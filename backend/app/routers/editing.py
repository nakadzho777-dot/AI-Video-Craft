"""編集支援 API.

- POST /editing/suggest : AI編集提案（カット/テロップ/BGM/テンポ/ショート化）
- POST /editing/probe   : 動画情報取得（FFmpeg）
- POST /editing/silence : 無音検出（FFmpeg）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai.runtime import build_provider, resolve_model
from ..auth.deps import get_current_user
from ..db.database import get_session
from ..db.models import Project, ProjectStatus, User
from ..editing.models import (
    ProbeResponse,
    SilenceRangeOut,
    SilenceRequest,
    SuggestRequest,
    SuggestResponse,
)
from ..editing.service import EditingSuggestService, SuggestParseError
from ..license.guard import (
    enforce_advanced_editing,
    enforce_ai_quota,
    enforce_provider_allowed,
    enforce_export_resolution,
    enforce_video_duration,
    record_ai_run,
)
from ..license.manager import limits_for_user
from ..logging_conf import get_logger
from ..video.ffmpeg import FFmpegError, FFmpegService

logger = get_logger(__name__)
router = APIRouter(prefix="/editing", tags=["editing"])


class ProbeRequest(BaseModel):
    input_path: str


class ExportRequest(BaseModel):
    input_path: str
    output_path: str
    height: int | None = None   # 出力の高さ(px)。None なら元のまま
    vertical: bool = False       # 縦動画化（ショート）— 高度編集


async def _require_ffmpeg() -> FFmpegService:
    ffmpeg = FFmpegService()
    if not await ffmpeg.is_available():
        raise HTTPException(
            503,
            "FFmpeg が見つかりません。FFmpeg をインストールし、PATH を通してください。",
        )
    return ffmpeg


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    req: SuggestRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SuggestResponse:
    limits = limits_for_user(user, session)
    # 1) プロジェクトから台本/企画を文脈として取り込む
    project: Project | None = None
    if req.project_id is not None:
        project = session.get(Project, req.project_id)
        if not project or project.owner_user_id != user.id:
            raise HTTPException(404, "プロジェクトが見つかりません")
        if not req.script and project.script_text:
            req.script = project.script_text
        if req.duration_sec <= 0 and project.plan_json:
            try:
                plan = json.loads(project.plan_json)
                req.duration_sec = float(plan.get("target_duration_sec", 0) or 0)
            except (json.JSONDecodeError, ValueError):
                pass

    # 2) プロバイダー / モデル解決 + プラン制限
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    enforce_ai_quota(limits, session, user.id)
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    # 3) 提案生成
    service = EditingSuggestService(provider)
    try:
        suggestion = await service.suggest(req, model=model)
    except SuggestParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("edit suggestion failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"編集提案の生成に失敗しました: {detail}") from e
    record_ai_run(session, user.id)

    # 4) 任意で保存
    saved: int | None = None
    if project is not None:
        project.edit_plan_json = suggestion.model_dump_json()
        project.status = ProjectStatus.EDITING
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        saved = project.id

    return SuggestResponse(
        suggestion=suggestion, provider=provider_id, model=model, saved_to_project=saved
    )


@router.post("/probe", response_model=ProbeResponse)
async def probe(
    req: ProbeRequest, user: User = Depends(get_current_user)
) -> ProbeResponse:
    ffmpeg = await _require_ffmpeg()
    try:
        info = await ffmpeg.probe(req.input_path)
    except FFmpegError as e:
        raise HTTPException(400, f"動画の読み込みに失敗しました: {e}") from e
    return ProbeResponse(
        duration_sec=info.duration_sec, width=info.width, height=info.height
    )


@router.post("/export")
async def export_video(
    req: ExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    limits = limits_for_user(user, session)
    # プラン制限（FFmpeg 実行前にチェックできるものを先に）
    if req.vertical:
        enforce_advanced_editing(limits, "縦動画化（ショート生成）")
    enforce_export_resolution(limits, req.height)

    ffmpeg = await _require_ffmpeg()

    # 尺の上限は実測が必要なので probe してから確認する
    try:
        info = await ffmpeg.probe(req.input_path)
    except FFmpegError as e:
        raise HTTPException(400, f"動画の読み込みに失敗しました: {e}") from e
    enforce_video_duration(limits, info.duration_sec)

    try:
        if req.vertical:
            out = await ffmpeg.to_vertical(req.input_path, req.output_path)
        else:
            out = await ffmpeg.export(req.input_path, req.output_path, height=req.height)
    except FFmpegError as e:
        raise HTTPException(400, f"書き出しに失敗しました: {e}") from e
    return {"output_path": str(out)}


@router.post("/silence", response_model=list[SilenceRangeOut])
async def detect_silence(
    req: SilenceRequest, user: User = Depends(get_current_user)
) -> list[SilenceRangeOut]:
    ffmpeg = await _require_ffmpeg()
    try:
        ranges = await ffmpeg.detect_silence(
            req.input_path,
            noise_db=req.noise_db,
            min_silence_sec=req.min_silence_sec,
        )
    except FFmpegError as e:
        raise HTTPException(400, f"無音検出に失敗しました: {e}") from e
    return [
        SilenceRangeOut(
            start_sec=r.start_sec, end_sec=r.end_sec, duration_sec=r.duration_sec
        )
        for r in ranges
    ]
