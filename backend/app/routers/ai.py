"""AI 関連 API.

プロバイダー一覧 / モデル一覧 / 接続確認 / チャット。
UI は具体プロバイダーに依存せず、このルーター経由で AI を利用する。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai import registry
from ..ai.base import ChatMessage
from ..ai.config_store import ai_config
from ..ai.runtime import build_provider, resolve_model
from ..deps import get_device_id
from ..db.database import get_session
from ..license.guard import enforce_provider_allowed
from ..license.manager import limits_for_device
from ..logging_conf import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


class ProviderInfoOut(BaseModel):
    id: str
    display_name: str
    kind: str
    download_url: str | None = None
    api_key_help_url: str | None = None
    configured: bool


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    provider: str | None = None      # 未指定なら既定プロバイダー
    model: str | None = None         # 未指定なら既定モデル
    messages: list[ChatTurn]
    temperature: float = 0.7


class ChatResponse(BaseModel):
    text: str
    provider: str
    model: str


@router.get("/providers", response_model=list[ProviderInfoOut])
def list_providers() -> list[ProviderInfoOut]:
    out: list[ProviderInfoOut] = []
    for info in registry.list_infos():
        cfg = ai_config.get(info.id)
        # ローカルはキー不要、API 系はキー有無で判定
        configured = info.kind.value == "local" or bool(cfg.api_key)
        out.append(
            ProviderInfoOut(
                id=info.id,
                display_name=info.display_name,
                kind=info.kind.value,
                download_url=info.download_url,
                api_key_help_url=info.api_key_help_url,
                configured=configured,
            )
        )
    return out


@router.get("/providers/{provider_id}/models", response_model=list[str])
async def list_models(provider_id: str) -> list[str]:
    try:
        _, provider = build_provider(provider_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    try:
        return await provider.list_models()
    except Exception as e:  # 疎通失敗など
        logger.warning("list_models failed for %s: %s", provider_id, e)
        raise HTTPException(502, f"モデル一覧の取得に失敗しました: {e}") from e


@router.get("/providers/{provider_id}/available")
async def check_available(provider_id: str) -> dict:
    try:
        _, provider = build_provider(provider_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"available": await provider.is_available()}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> ChatResponse:
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    # Free版は無料AI（ローカル）のみ。チャットにも適用する。
    enforce_provider_allowed(limits_for_device(device_id, session), provider)

    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    messages = [ChatMessage(role=t.role, content=t.content) for t in req.messages]
    try:
        result = await provider.chat(
            messages, model=model, temperature=req.temperature
        )
    except Exception as e:
        logger.exception("chat failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"AI生成に失敗しました: {detail}") from e

    return ChatResponse(text=result.text, provider=result.provider, model=result.model)
