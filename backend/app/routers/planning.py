"""AI企画 API.

テーマから動画企画（タイトル/構成/尺配分/掴み/CTA/サムネイル案）を生成する。
project_id 指定時はプロジェクトの plan_json へ保存する。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..ai.runtime import build_provider, resolve_model
from ..auth.deps import get_current_user
from ..db.database import get_session
from ..db.models import Project, ProjectStatus, User
from ..license.guard import (
    enforce_ai_quota,
    enforce_provider_allowed,
    record_ai_run,
)
from ..license.manager import limits_for_user
from ..logging_conf import get_logger
from ..planning.models import PlanRequest, PlanResponse
from ..planning.service import PlanningService, PlanParseError

logger = get_logger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])


@router.post("/generate", response_model=PlanResponse)
async def generate_plan(
    req: PlanRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PlanResponse:
    limits = limits_for_user(user, session)
    # 1) プロバイダー / モデル解決 + プラン制限
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

    # 2) 企画生成
    service = PlanningService(provider)
    try:
        plan = await service.generate(req, model=model)
    except PlanParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("plan generation failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"企画生成に失敗しました: {detail}") from e
    record_ai_run(session, user.id)

    # 3) 任意でプロジェクトへ保存
    saved: int | None = None
    if req.project_id is not None:
        project = session.get(Project, req.project_id)
        if not project or project.owner_user_id != user.id:
            raise HTTPException(404, "保存先プロジェクトが見つかりません")
        project.plan_json = plan.model_dump_json()
        project.status = ProjectStatus.MATERIALS  # 企画完了 → 素材フェーズへ
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        saved = project.id

    return PlanResponse(
        plan=plan, provider=provider_id, model=model, saved_to_project=saved
    )
