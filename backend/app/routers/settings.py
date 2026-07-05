"""設定 API.

AIプロバイダーのAPIキー設定 / 既定プロバイダー・モデル選択 / ライセンスキー。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai import registry
from ..ai.config_store import ai_config
from ..auth.deps import get_current_user
from ..db.database import get_session
from ..db.models import User
from ..license.manager import (
    limits_for_user,
    plan_for_user,
    subscription_days_remaining,
)
from ..license.service import get_user_license
from ..license.usage import get_ai_runs_today

router = APIRouter(prefix="/settings", tags=["settings"])


class ApiKeyIn(BaseModel):
    api_key: str | None = None


class DefaultModelIn(BaseModel):
    model: str | None = None


class DefaultProviderIn(BaseModel):
    provider: str


@router.put("/ai/{provider_id}/api-key")
def set_api_key(provider_id: str, payload: ApiKeyIn) -> dict:
    if provider_id not in registry.available_ids():
        raise HTTPException(404, f"Unknown provider '{provider_id}'")
    ai_config.set_api_key(provider_id, payload.api_key)
    return {"ok": True, "provider": provider_id, "configured": bool(payload.api_key)}


@router.put("/ai/{provider_id}/default-model")
def set_default_model(provider_id: str, payload: DefaultModelIn) -> dict:
    if provider_id not in registry.available_ids():
        raise HTTPException(404, f"Unknown provider '{provider_id}'")
    ai_config.set_default_model(provider_id, payload.model)
    return {"ok": True, "provider": provider_id, "default_model": payload.model}


@router.put("/ai/default-provider")
def set_default_provider(payload: DefaultProviderIn) -> dict:
    if payload.provider not in registry.available_ids():
        raise HTTPException(404, f"Unknown provider '{payload.provider}'")
    ai_config.default_provider = payload.provider
    return {"ok": True, "default_provider": payload.provider}


@router.get("/usage")
def get_usage(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """現在のプラン・制限・本日のAI利用状況を返す（アカウント単位）。"""
    plan = plan_for_user(user, session)
    limits = limits_for_user(user, session)
    used = get_ai_runs_today(session, user.id)
    limit = limits.ai_runs_per_day

    lic = get_user_license(session, user)
    lic_kind = lic.kind if lic else None
    lic_exp = lic.expires_at.isoformat() if lic and lic.expires_at else None
    days_left = (
        subscription_days_remaining(lic, session) if lic else None
    )
    return {
        "plan": plan.value,
        "limits": limits.__dict__,
        "ai_runs_today": used,
        "ai_runs_limit": limit,
        "ai_runs_remaining": None if limit is None else max(0, limit - used),
        # サブスク更新リマインド用
        "license_kind": lic_kind,
        "license_expires_at": lic_exp,
        "license_expires_in_days": days_left,
    }
