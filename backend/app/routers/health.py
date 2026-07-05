"""ヘルスチェック / システム状態。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import get_settings
from ..video.ffmpeg import FFmpegService

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    """基本的な稼働確認（アカウント非依存）。プランは /settings/usage を参照。"""
    ffmpeg = FFmpegService()
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg_available": await ffmpeg.is_available(),
        "dev_mode": get_settings().dev_mode,
    }
