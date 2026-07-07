"""AI利用回数の日次カウンタ（PC/デバイス単位）.

Free版の「AI制作 1日5回」制限のため、デバイス×日付ごとに回数を記録する。
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from ..db.models import UsageRecord


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_ai_runs_today(session: Session, device_id: str) -> int:
    row = session.exec(
        select(UsageRecord).where(
            UsageRecord.device_id == device_id, UsageRecord.date == _today()
        )
    ).first()
    return row.ai_runs if row else 0


def increment_ai_run(session: Session, device_id: str) -> int:
    """本日のAI利用回数を +1 して返す。"""
    today = _today()
    row = session.exec(
        select(UsageRecord).where(
            UsageRecord.device_id == device_id, UsageRecord.date == today
        )
    ).first()
    if row is None:
        row = UsageRecord(device_id=device_id, date=today, ai_runs=0)
    row.ai_runs += 1
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.ai_runs
