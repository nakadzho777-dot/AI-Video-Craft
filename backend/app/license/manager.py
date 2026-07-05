"""ライセンス管理.

Free: ライセンス不要 / 各種制限あり
Pro : ライセンスキー引き換え / 1ライセンス2台まで

プラン・制限は **アカウント単位** で解決する。
制限値を一元管理し、機能側は Limits を参照するだけにする。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from datetime import timezone

from sqlmodel import Session, select

from ..db.models import License, User
from .clock import effective_now


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"


@dataclass(frozen=True)
class Limits:
    """プランごとの制限。"""

    max_projects: int | None       # None = 無制限
    ai_runs_per_day: int | None
    max_resolution_p: int | None   # 720, 2160(4K) など
    max_video_minutes: int | None
    advanced_editing: bool
    timeline_tracks: int | None
    paid_ai_allowed: bool          # 有料AI（API）利用可否


FREE_LIMITS = Limits(
    max_projects=1,
    ai_runs_per_day=5,
    max_resolution_p=720,
    max_video_minutes=5,
    advanced_editing=False,
    timeline_tracks=1,
    paid_ai_allowed=False,
)

PRO_LIMITS = Limits(
    max_projects=None,
    ai_runs_per_day=None,
    max_resolution_p=2160,
    max_video_minutes=None,
    advanced_editing=True,
    timeline_tracks=None,
    paid_ai_allowed=True,
)


def license_is_active(lic: License, session: Session) -> bool:
    """ライセンスが現在有効か（サブスクは失効判定を含む）。"""
    if lic.kind == "subscription" and lic.expires_at is not None:
        exp = lic.expires_at
        if exp.tzinfo is None:  # 素朴なdatetimeはUTC扱い
            exp = exp.replace(tzinfo=timezone.utc)
        return effective_now(session) <= exp
    return True  # 買い切り / 期限なし


def plan_for_user(user: User, session: Session) -> Plan:
    """アカウントが有効なライセンスを持っていれば Pro（サブスク失効はFree）。"""
    lic = session.exec(
        select(License).where(License.redeemed_by_user_id == user.id)
    ).first()
    if lic and license_is_active(lic, session):
        return Plan.PRO
    return Plan.FREE


def subscription_days_remaining(lic: License, session: Session) -> int | None:
    """サブスクの残り日数（切れていれば負値）。サブスク以外は None。"""
    if lic.kind != "subscription" or lic.expires_at is None:
        return None
    exp = lic.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - effective_now(session)
    # 切り上げ（残り12時間なら「1日」）
    import math

    return math.ceil(delta.total_seconds() / 86400)


def limits_for_user(user: User, session: Session) -> Limits:
    return PRO_LIMITS if plan_for_user(user, session) is Plan.PRO else FREE_LIMITS
