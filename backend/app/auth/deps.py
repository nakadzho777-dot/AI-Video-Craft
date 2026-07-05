"""認証の依存性（現在のユーザー取得）.

Authorization: Bearer <token> からユーザーを解決する。
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import AuthToken, User


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """ログイン必須エンドポイント用。未認証なら 401。"""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ログインが必要です")
    row = session.exec(select(AuthToken).where(AuthToken.token == token)).first()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "セッションが無効です")
    user = session.get(User, row.user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "アカウントが見つかりません")
    return user
