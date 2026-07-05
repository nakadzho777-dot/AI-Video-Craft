"""時計の巻き戻し対策（anti-rollback）.

サブスクの失効判定はローカル時計に依存するため、
「これまでに観測した最新時刻」を記録し、時計が戻っても失効判定が
甘くならないようにする（effective_now は単調非減少）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..db.models import AppState

_LAST_SEEN_KEY = "last_seen_utc"


def effective_now(session: Session) -> datetime:
    """システム時刻と記録済み最新時刻の大きい方を返し、記録を更新する。"""
    now = datetime.now(timezone.utc)
    row = session.exec(
        select(AppState).where(AppState.key == _LAST_SEEN_KEY)
    ).first()

    last_seen: datetime | None = None
    if row and row.value:
        try:
            last_seen = datetime.fromisoformat(row.value)
        except ValueError:
            last_seen = None

    eff = now if last_seen is None else max(now, last_seen)

    # 記録を単調に更新
    if row is None:
        row = AppState(key=_LAST_SEEN_KEY, value=eff.isoformat())
    else:
        row.value = eff.isoformat()
    session.add(row)
    session.commit()
    return eff
