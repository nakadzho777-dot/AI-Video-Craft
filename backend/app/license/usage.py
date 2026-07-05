"""AI利用回数の日次カウンタ（アカウント単位）.

Free版の「AI制作 1日5回」制限のため、ユーザー×日付ごとに回数を記録する。
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from ..db.models import UsageRecord


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_ai_runs_today(session: Session, user_id: int) -> int:
    row = session.exec(
        select(UsageRecord).where(
            UsageRecord.user_id == user_id, UsageRecord.date == _today()
        )
    ).first()
    return row.ai_runs if row else 0


def increment_ai_run(session: Session, user_id: int) -> int:
    """本日のAI利用回数を +1 して返す。"""
    today = _today()
    row = session.exec(
        select(UsageRecord).where(
            UsageRecord.user_id == user_id, UsageRecord.date == today
        )
    ).first()
    if row is None:
        row = UsageRecord(user_id=user_id, date=today, ai_runs=0)
    row.ai_runs += 1
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.ai_runs
