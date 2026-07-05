"""認証 API（登録 / ログイン / ログアウト / 自分の情報）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth.deps import get_current_user
from ..auth.security import hash_password, new_token, verify_password
from ..db.database import get_session
from ..db.models import AuthToken, User
from ..license.manager import plan_for_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    password: str
    username: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    plan: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


def _user_out(user: User, session: Session) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        plan=plan_for_user(user, session).value,
    )


def _issue_token(session: Session, user: User) -> str:
    token = new_token()
    session.add(AuthToken(token=token, user_id=user.id))
    session.commit()
    return token


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, session: Session = Depends(get_session)) -> AuthOut:
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "メールアドレスの形式が正しくありません")
    if len(payload.password) < 8:
        raise HTTPException(400, "パスワードは8文字以上にしてください")
    exists = session.exec(select(User).where(User.email == email)).first()
    if exists:
        raise HTTPException(409, "このメールアドレスは既に登録されています")

    user = User(
        email=email,
        username=payload.username or email.split("@")[0],
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = _issue_token(session, user)
    return AuthOut(token=token, user=_user_out(user, session))


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, session: Session = Depends(get_session)) -> AuthOut:
    email = payload.email.lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "メールアドレスまたはパスワードが違います")
    token = _issue_token(session, user)
    return AuthOut(token=token, user=_user_out(user, session))


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2:
            row = session.exec(
                select(AuthToken).where(AuthToken.token == parts[1].strip())
            ).first()
            if row:
                session.delete(row)
                session.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> UserOut:
    return _user_out(user, session)
