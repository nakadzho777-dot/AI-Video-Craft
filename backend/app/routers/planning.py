"""AI企画 API.

テーマから動画企画（タイトル/構成/尺配分/掴み/CTA/サムネイル案）を生成する。
project_id 指定時はプロジェクトの plan_json へ保存する。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..planning.models import VideoPlan

from ..ai.base import ChatMessage
from ..ai.structured import chat_json
from ..ai.runtime import build_provider, resolve_model
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
from ..planning.models import PlanRequest, PlanResponse
from ..planning.service import PlanningService, PlanParseError

logger = get_logger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])


@router.post("/generate", response_model=PlanResponse)
async def generate_plan(
    req: PlanRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> PlanResponse:
    limits = limits_for_device(device_id, session)
    # 1) プロバイダー / モデル解決 + プラン制限
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

    # 2) 同じプロジェクト・同じテーマで過去に決定した企画があれば、
    #    別バリエーションを作らせるため要約を渡す
    previous = _previous_summaries(session, req.project_id, device_id, req.topic)

    # 3) 企画生成
    service = PlanningService(provider)
    try:
        plan = await service.generate(req, model=model, previous=previous)
    except PlanParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("plan generation failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"企画生成に失敗しました: {detail}") from e
    record_ai_run(session, device_id)

    # 保存は明示的な「決定」操作（/planning/save）で行う
    return PlanResponse(
        plan=plan, provider=provider_id, model=model, saved_to_project=None
    )


# ============================================================
# 企画の保存（「決定」時）＋履歴
# ============================================================
def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _plan_summary(plan: VideoPlan) -> str:
    titles = " / ".join(plan.titles[:2])
    secs = "→".join(s.name for s in plan.sections[:5])
    return (
        f"[{plan.format}/{plan.target_duration_sec}秒] {titles}"
        f"｜掴み: {plan.hook[:40]}｜構成: {secs}"
    )


def _previous_summaries(
    session: Session, project_id: int | None, device_id: str, topic: str
) -> list[str]:
    """同じプロジェクト・同じテーマで決定済みの企画の要約一覧。"""
    if project_id is None:
        return []
    project = session.get(Project, project_id)
    if not project or project.device_id != device_id:
        return []
    try:
        history = json.loads(project.plan_history_json or "[]")
    except Exception:
        history = []
    out: list[str] = []
    for h in history:
        if _norm(h.get("topic", "")) == _norm(topic):
            out.append(h.get("summary", ""))
    return [s for s in out if s]


class PlanSaveRequest(BaseModel):
    project_id: int
    plan: VideoPlan
    notes: str = ""


class PlanSaveResponse(BaseModel):
    project_id: int
    variation_count: int  # このテーマで決定した企画の通算数


@router.post("/save", response_model=PlanSaveResponse)
def save_plan(
    req: PlanSaveRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> PlanSaveResponse:
    """生成した企画を「決定」してプロジェクトへ保存し、履歴へ追記する。"""
    project = session.get(Project, req.project_id)
    if not project or project.device_id != device_id:
        raise HTTPException(404, "保存先プロジェクトが見つかりません")

    try:
        history = json.loads(project.plan_history_json or "[]")
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []
    history.append(
        {
            "topic": req.plan.topic,
            "notes": req.notes,
            "summary": _plan_summary(req.plan),
        }
    )

    project.plan_json = req.plan.model_dump_json()
    project.plan_history_json = json.dumps(history, ensure_ascii=False)
    project.target_duration_sec = req.plan.target_duration_sec or project.target_duration_sec
    project.status = ProjectStatus.MATERIALS  # 企画完了 → 素材フェーズへ
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)
    session.commit()

    count = sum(1 for h in history if _norm(h.get("topic", "")) == _norm(req.plan.topic))
    return PlanSaveResponse(project_id=project.id, variation_count=count)


# ============================================================
# 尺の候補（生成前に、動画用/ショート用の目標尺を提案）
# ============================================================
class DurationRequest(BaseModel):
    topic: str = ""
    notes: str = ""        # ユーザーの指示
    provider: str | None = None
    model: str | None = None


class DurationResponse(BaseModel):
    video_sec: int         # 通常動画の目標尺
    short_sec: int         # ショート動画の目標尺
    note: str = ""
    record_video_sec: int  # 録画の目安（カット分を見込んで長め）
    record_short_sec: int


_DURATION_SYS = """あなたは動画尺のアドバイザーです。テーマ/指示から完成動画の適切な長さを2案提案します。
出力は必ず次のJSONのみ:
{"video_sec": 通常動画の秒数, "short_sec": ショート動画の秒数, "note": "一言理由"}
- video_sec は内容量に見合う長さ（短すぎず冗長すぎず。目安 60〜900）。
- short_sec は 15〜60 の範囲。
"""


@router.post("/durations", response_model=DurationResponse)
async def suggest_durations(
    req: DurationRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> DurationResponse:
    # 尺候補は「必ず出す」。プロバイダー未設定・モデル解決失敗・ネット不通・JSON崩れなど
    # 何が起きても、目安の既定値でフォールバックして候補を返す（エラーで空にしない）。
    fallback = {
        "video_sec": 240,
        "short_sec": 45,
        "note": "AIに繋がらなかったため、目安の候補を表示しています。",
    }
    user = f"テーマ: {req.topic or '(未指定)'}\n指示/補足: {req.notes or '(なし)'}"
    messages = [
        ChatMessage(role="system", content=_DURATION_SYS),
        ChatMessage(role="user", content=user),
    ]
    data = fallback
    try:
        limits = limits_for_device(device_id, session)
        provider_id, provider = build_provider(req.provider)
        enforce_provider_allowed(limits, provider)
        enforce_ai_quota(limits, session, device_id)
        model = await resolve_model(provider, provider_id, req.model)
        data = await chat_json(provider, messages, model=model, temperature=0.4)
        record_ai_run(session, device_id)
    except Exception as e:
        # 尺候補はあくまで目安。未設定/クォータ超過/ネット不通/JSON崩れ 何が起きても
        # 目安の候補を返す（AI未使用なのでクォータも消費しない）。
        logger.info("尺候補はフォールバック（%s）", e)
        data = fallback

    def _num(v, default):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    video_sec = max(15, _num(data.get("video_sec"), 240))
    short_sec = min(60, max(10, _num(data.get("short_sec"), 45)))
    return DurationResponse(
        video_sec=video_sec,
        short_sec=short_sec,
        note=str(data.get("note", "")),
        # 録画はカット編集を見込んで長めに撮る
        record_video_sec=round(video_sec * 1.3),
        record_short_sec=round(short_sec * 1.4),
    )
