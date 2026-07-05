"""投稿支援 API.

企画（あれば）を元に、各プラットフォーム向けの投稿テキストを生成する。
project_id 指定時は企画を参照し、生成結果を publish_json へ保存する。
"""
from __future__ import annotations

import json
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
from ..planning.summary import summarize_plan
from ..publishing.models import PublishRequest, PublishResponse
from ..publishing.service import PublishingService, PublishParseError

logger = get_logger(__name__)
router = APIRouter(prefix="/publishing", tags=["publishing"])


@router.post("/generate", response_model=PublishResponse)
async def generate_publish(
    req: PublishRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublishResponse:
    limits = limits_for_user(user, session)
    # 1) プロジェクトがあれば企画を文脈にする
    project: Project | None = None
    plan_summary = ""
    topic = req.topic
    if req.project_id is not None:
        project = session.get(Project, req.project_id)
        if not project or project.owner_user_id != user.id:
            raise HTTPException(404, "プロジェクトが見つかりません")
        if project.plan_json:
            try:
                plan = json.loads(project.plan_json)
                plan_summary = summarize_plan(plan)
                topic = topic or plan.get("topic", "")
            except (json.JSONDecodeError, AttributeError):
                logger.warning("plan_json の解析に失敗しました (project %s)", project.id)
        topic = topic or project.title

    if not topic and not plan_summary:
        raise HTTPException(
            400, "topic または企画済みの project_id を指定してください"
        )

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

    # 3) 生成
    service = PublishingService(provider)
    req.topic = topic
    try:
        pack = await service.generate(req, model=model, plan_summary=plan_summary)
    except PublishParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("publish generation failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"投稿テキストの生成に失敗しました: {detail}") from e
    record_ai_run(session, user.id)

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
        pack=pack, provider=provider_id, model=model, saved_to_project=saved
    )
