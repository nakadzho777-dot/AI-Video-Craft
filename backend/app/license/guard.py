"""プラン制限の適用（ガード）.

各機能ルーターから呼び出し、Free/Pro の制限を **アカウント単位** で適用する。
制限値(Limits)は呼び出し側で limits_for_user() から解決して渡す。
超過時は 402 (Payment Required) を返す。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session

from ..ai.base import AIProvider, ProviderKind
from .manager import Limits
from .usage import get_ai_runs_today, increment_ai_run


def _pay(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail)


def enforce_provider_allowed(limits: Limits, provider: AIProvider) -> None:
    """Free版は無料AI（ローカル）のみ。有料APIプロバイダーを拒否する。"""
    if limits.paid_ai_allowed:
        return
    if provider.kind != ProviderKind.LOCAL:
        raise _pay(
            "Free版では無料AI（Ollama等のローカル）のみ利用できます。"
            "Pro版で OpenAI / Gemini / Claude が使えます。"
        )


def enforce_ai_quota(limits: Limits, session: Session, device_id: str) -> None:
    """Free版のAI制作 1日回数を超えていないか確認する（記録はしない）。"""
    limit = limits.ai_runs_per_day
    if limit is None:  # Pro は無制限
        return
    used = get_ai_runs_today(session, device_id)
    if used >= limit:
        raise _pay(
            f"Free版のAI制作は1日{limit}回までです（本日{used}回使用）。"
            "Pro版で無制限になります。"
        )


def record_ai_run(session: Session, device_id: str) -> None:
    """AI制作の利用を1回記録する（生成成功後に呼ぶ）。"""
    increment_ai_run(session, device_id)


def enforce_export_resolution(limits: Limits, height: int | None) -> None:
    """Free版の書き出し解像度上限（720p）を適用する。"""
    max_p = limits.max_resolution_p
    if max_p is not None and height is not None and height > max_p:
        raise _pay(
            f"Free版の書き出しは{max_p}pまでです（要求 {height}p）。"
            "Pro版で4Kまで書き出せます。"
        )


def enforce_video_duration(limits: Limits, duration_sec: float) -> None:
    """Free版の動画尺上限（5分）を適用する。"""
    max_min = limits.max_video_minutes
    if max_min is not None and duration_sec > max_min * 60:
        raise _pay(
            f"Free版は{max_min}分までの動画に対応します"
            f"（この動画は約{duration_sec / 60:.1f}分）。"
            "Pro版で長時間動画を書き出せます。"
        )


def enforce_advanced_editing(limits: Limits, feature: str = "この機能") -> None:
    """高度編集（縦動画化/ショート生成など）を Pro 限定にする。"""
    if not limits.advanced_editing:
        raise _pay(f"{feature}はPro版の高度編集機能です。Pro版でご利用いただけます。")
