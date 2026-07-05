"""宣伝AI API（開発者専用）.

記事・SEOコンテンツを量産する。開発モード(dev_mode)でのみ利用可能。
エンドユーザー環境では 403 を返し、機能を露出しない。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..ai.runtime import build_provider, resolve_model
from ..config import get_settings
from ..logging_conf import get_logger
from ..marketing.models import MarketingRequest, MarketingResponse
from ..marketing.service import MarketingError, MarketingService

logger = get_logger(__name__)
router = APIRouter(prefix="/marketing", tags=["marketing (dev)"])


def require_dev_mode() -> None:
    """開発モード以外ではアクセスを拒否する。"""
    if not get_settings().dev_mode:
        raise HTTPException(
            403,
            "宣伝AIは開発者専用機能です（開発モードで有効化してください）。",
        )


@router.post(
    "/generate",
    response_model=MarketingResponse,
    dependencies=[Depends(require_dev_mode)],
)
async def generate_articles(req: MarketingRequest) -> MarketingResponse:
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    service = MarketingService(provider)
    try:
        articles = await service.generate_batch(req, model=model)
    except MarketingError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("marketing generation failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"宣伝記事の生成に失敗しました: {detail}") from e

    requested = len(req.keywords) if req.keywords else req.count
    return MarketingResponse(
        articles=articles,
        provider=provider_id,
        model=model,
        requested=requested,
        generated=len(articles),
    )
