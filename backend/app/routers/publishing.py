"""投稿支援 API.

企画（あれば）を元に、各プラットフォーム向けの投稿テキストを生成する。
project_id 指定時は企画を参照し、生成結果を publish_json へ保存する。
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai.base import ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.runtime import build_provider, resolve_model
from ..ai.structured import chat_json
from ..config import get_settings
from ..editing.editor import extract_frame_at, extract_frames
from ..deps import get_device_id
from ..db.database import get_session
from ..db.models import Project, ProjectStatus
from ..license.guard import (
    enforce_ai_quota,
    enforce_provider_allowed,
    record_ai_run,
)
from ..license.manager import limits_for_device
from ..logging_conf import get_logger
from ..planning.summary import summarize_plan
from ..publishing.models import PublishRequest, PublishResponse
from ..publishing.service import PublishingService, PublishParseError
from ..publishing.thumbnail import (
    THUMB_SUGGEST_SYS,
    ThumbSpec,
    build_suggest_user,
    render_thumbnail,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/publishing", tags=["publishing"])


@router.post("/generate", response_model=PublishResponse)
async def generate_publish(
    req: PublishRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> PublishResponse:
    limits = limits_for_device(device_id, session)
    # 1) プロジェクトがあれば企画を文脈にする
    project: Project | None = None
    plan_summary = ""
    topic = req.topic
    if req.project_id is not None:
        project = session.get(Project, req.project_id)
        if not project or project.device_id != device_id:
            raise HTTPException(404, "プロジェクトが見つかりません")
        if project.plan_json:
            try:
                plan = json.loads(project.plan_json)
                plan_summary = summarize_plan(plan)
                topic = topic or plan.get("topic", "")
            except (json.JSONDecodeError, AttributeError):
                logger.warning("plan_json の解析に失敗しました (project %s)", project.id)
        topic = topic or project.title

    if not topic and not plan_summary and not req.video_path.strip():
        raise HTTPException(
            400, "topic / 企画済みの project_id / 動画 のいずれかを指定してください"
        )

    # 2) プロバイダー / モデル解決 + プラン制限
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    enforce_ai_quota(limits, session, device_id)
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    # 2.5) 動画があればフレームを抽出してAIが内容を確認
    video_analysis = ""
    if req.video_path.strip():
        if not getattr(provider, "supports_vision", False):
            raise HTTPException(
                400,
                "動画の内容確認は Gemini など画像対応プロバイダーが必要です（設定で切替）。",
            )
        try:
            import asyncio

            frames = await asyncio.to_thread(extract_frames, req.video_path.strip(), 5)
            if not frames:
                raise HTTPException(400, "動画を読み込めませんでした。")
            video_analysis = await provider.analyze_images(
                "これはある動画から等間隔で抜き出した複数のフレームです。"
                "この動画が何の動画か、何が映っているか、雰囲気・ジャンルを"
                "日本語で簡潔に（3〜5文で）要約してください。投稿文の作成に使います。",
                frames,
                model=model,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("video analysis failed")
            raise HTTPException(502, f"動画の内容確認に失敗しました: {e}") from e

    # 3) 生成
    service = PublishingService(provider)
    req.topic = topic
    try:
        pack = await service.generate(
            req, model=model, plan_summary=plan_summary,
            video_analysis=video_analysis,
        )
    except PublishParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("publish generation failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"投稿テキストの生成に失敗しました: {detail}") from e
    record_ai_run(session, device_id)

    # 4) 任意で保存
    saved: int | None = None
    if project is not None:
        project.publish_json = pack.model_dump_json()
        project.status = ProjectStatus.PUBLISHING
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        saved = project.id

    return PublishResponse(
        pack=pack, provider=provider_id, model=model, saved_to_project=saved,
        video_analysis=video_analysis,
    )


# ============================================================
# サムネイル作業場
# ============================================================
def _thumb_dir() -> str:
    d = str(get_settings().data_dir / "thumbnails")
    return d


class SceneRequest(BaseModel):
    video_path: str
    time_sec: float = 0.0


@router.post("/thumbnail/scene")
async def thumbnail_scene(req: SceneRequest) -> dict:
    """動画の指定シーンを1枚切り出してサムネのベース画像にする（AI不要）。"""
    if not req.video_path.strip():
        raise HTTPException(400, "動画のパスが必要です。")
    jpg = await asyncio.to_thread(
        extract_frame_at, req.video_path.strip(), req.time_sec, 1280
    )
    if not jpg:
        raise HTTPException(400, "動画からフレームを取得できませんでした。")
    out = f"{_thumb_dir()}/scene_{int(time.time() * 1000)}.jpg"
    import os

    os.makedirs(_thumb_dir(), exist_ok=True)
    with open(out, "wb") as f:
        f.write(jpg)
    return {"image_path": out}


class ThumbSuggestRequest(BaseModel):
    topic: str = ""
    notes: str = ""
    video_analysis: str = ""
    provider: str | None = None
    model: str | None = None


@router.post("/thumbnail/suggest")
async def thumbnail_suggest(
    req: ThumbSuggestRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> dict:
    """AIがサムネ用の短い文言（大見出し・補足）を提案する。"""
    limits = limits_for_device(device_id, session)
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    enforce_ai_quota(limits, session, device_id)
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    messages = [
        ChatMessage(role="system", content=THUMB_SUGGEST_SYS),
        ChatMessage(
            role="user",
            content=build_suggest_user(req.topic, req.notes, req.video_analysis or None),
        ),
    ]
    try:
        data = await chat_json(provider, messages, model=model, temperature=0.8)
    except JsonExtractError as e:
        raise HTTPException(422, f"サムネ文言の解析に失敗しました: {e}") from e
    except Exception as e:
        logger.exception("thumbnail suggest failed")
        raise HTTPException(502, f"サムネ文言の生成に失敗しました: {e}") from e
    record_ai_run(session, device_id)
    return {
        "title": str(data.get("title", "")).strip(),
        "subtitle": str(data.get("subtitle", "")).strip(),
    }


class ThumbGenRequest(BaseModel):
    prompt: str
    provider: str | None = None
    model: str | None = None


@router.post("/thumbnail/generate")
async def thumbnail_generate(
    req: ThumbGenRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> dict:
    """AIでサムネ背景画像を生成する（対応プロバイダーのみ。失敗時は warning を返す）。"""
    if not req.prompt.strip():
        raise HTTPException(400, "生成したい画像の説明を入力してください。")
    limits = limits_for_device(device_id, session)
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    if not getattr(provider, "supports_image_gen", False):
        return {"image_path": "", "warning": "この設定では画像生成に未対応です（Gemini等が必要）。"}
    enforce_ai_quota(limits, session, device_id)
    try:
        img = await provider.generate_image(req.prompt.strip())
    except Exception as e:
        logger.info("image gen failed: %s", e)
        return {"image_path": "", "warning": f"画像生成に失敗しました（{e}）。グラデ背景で代替できます。"}
    import os

    os.makedirs(_thumb_dir(), exist_ok=True)
    out = f"{_thumb_dir()}/ai_{int(time.time() * 1000)}.png"
    with open(out, "wb") as f:
        f.write(img)
    record_ai_run(session, device_id)
    return {"image_path": out, "warning": ""}


@router.post("/thumbnail/render")
async def thumbnail_render(spec: ThumbSpec) -> dict:
    """指定内容でサムネイルPNGを描画して保存する（AI不要・プレビュー/確定共通）。"""
    out = f"{_thumb_dir()}/thumb_{int(time.time() * 1000)}.png"
    try:
        await asyncio.to_thread(render_thumbnail, spec, out)
    except Exception as e:
        logger.exception("thumbnail render failed")
        raise HTTPException(500, f"サムネイルの描画に失敗しました: {e}") from e
    return {"image_path": out}
