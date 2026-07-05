"""ライセンス API.

- POST /license/redeem      : キー引き換え + 端末登録（購入者）
- GET  /license/status      : 自分のライセンス・端末・プラン
- POST /license/devices/release : 端末登録の解除
- POST /license/issue       : キー発行（開発者/販売者・dev_mode のみ）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..auth.deps import get_current_user
from ..config import get_settings
from ..db.database import get_session
from ..db.models import User
from ..license import service
from ..license.keys import is_dev_public_key, is_dev_signing_key
from ..license.manager import license_is_active, plan_for_user
from ..license.offline import issue_offline_token
from ..license.signing import generate_keypair

router = APIRouter(prefix="/license", tags=["license"])


class RedeemIn(BaseModel):
    license_key: str
    device_id: str
    device_name: str = ""


class ReleaseIn(BaseModel):
    device_id: str


class IssueIn(BaseModel):
    count: int = 1
    booth_order_number: str | None = None


class DeviceOut(BaseModel):
    device_id: str
    device_name: str
    registered_at: str


class ActivateOfflineIn(BaseModel):
    license_token: str


class SignIn(BaseModel):
    email: str
    kind: str = "perpetual"       # perpetual | subscription
    days: int = 365               # subscription の有効日数


class LicenseStatusOut(BaseModel):
    plan: str
    has_license: bool
    license_key: str | None = None
    source: str | None = None
    max_devices: int | None = None
    devices: list[DeviceOut] = []
    kind: str | None = None
    expires_at: str | None = None


def _status(session: Session, user: User) -> LicenseStatusOut:
    lic = service.get_user_license(session, user)
    plan = plan_for_user(user, session).value
    if not lic:
        return LicenseStatusOut(plan=plan, has_license=False)
    devices = [
        DeviceOut(
            device_id=d.device_id,
            device_name=d.device_name,
            registered_at=d.registered_at.isoformat(),
        )
        for d in service.list_devices(session, lic.id)
    ]
    return LicenseStatusOut(
        plan=plan,
        has_license=True,
        license_key=lic.key,
        source=lic.source,
        max_devices=lic.max_devices,
        devices=devices,
        kind=lic.kind,
        expires_at=lic.expires_at.isoformat() if lic.expires_at else None,
    )


@router.get("/status", response_model=LicenseStatusOut)
def status_(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> LicenseStatusOut:
    return _status(session, user)


@router.post("/redeem", response_model=LicenseStatusOut)
def redeem(
    payload: RedeemIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    try:
        service.redeem_license(
            session, user, payload.license_key, payload.device_id, payload.device_name
        )
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return _status(session, user)


@router.post("/devices/release", response_model=LicenseStatusOut)
def release_device(
    payload: ReleaseIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    try:
        service.release_device(session, user, payload.device_id)
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return _status(session, user)


@router.post("/activate-offline", response_model=LicenseStatusOut)
def activate_offline(
    payload: ActivateOfflineIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    """署名ライセンス（オフライン）を有効化する。"""
    try:
        service.activate_offline(session, user, payload.license_token)
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return _status(session, user)


@router.post("/sign")
def sign(
    payload: SignIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """メールに紐づく署名ライセンスを発行する（販売者用）。開発モード限定。"""
    dev = get_settings().dev_mode
    if not dev:
        raise HTTPException(403, "署名発行は販売者専用機能です（開発モードで有効化）。")
    try:
        token = service.sign_for_email(
            payload.email, payload.kind, payload.days, dev_mode=dev
        )
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return {"license_token": token, "email": payload.email.strip().lower()}


@router.get("/offline-token")
def offline_token(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict:
    """オフライン利用トークンを返す（A+Bハイブリッド）。

    アプリはこれをキャッシュし、オフライン時に公開鍵で検証してPro状態を維持する。
    """
    lic = service.get_user_license(session, user)
    if not lic or not license_is_active(lic, session):
        return {"token": None}
    token = lic.signed_token or issue_offline_token(session, user, lic)
    return {"token": token}


@router.get("/signing-info")
def signing_info(user: User = Depends(get_current_user)) -> dict:
    """署名鍵の状態（実販売前の差し替え警告用）。開発モード限定。"""
    if not get_settings().dev_mode:
        raise HTTPException(403, "開発者専用機能です。")
    return {
        "using_dev_public_key": is_dev_public_key(),
        "using_dev_private_key": is_dev_signing_key(),
    }


@router.post("/keygen")
def keygen(user: User = Depends(get_current_user)) -> dict:
    """本番用の鍵ペアを生成する（表示のみ・保存しない）。開発モード限定。

    生成した鍵は環境変数に設定して使う（この端末には保存されない）。
    """
    if not get_settings().dev_mode:
        raise HTTPException(403, "開発者専用機能です。")
    private_key, public_key = generate_keypair()
    return {
        "public_key": public_key,
        "private_key": private_key,
        "instructions": {
            "public_env": "AIVC_LICENSE_PUBLIC_KEY",
            "private_env": "AIVC_LICENSE_PRIVATE_KEY",
            "note": (
                "公開鍵は配布アプリ側に、秘密鍵は署名する端末だけに設定してください。"
                "秘密鍵は二度と表示されないので安全に保管してください。"
            ),
        },
    }


@router.post("/issue")
def issue(
    payload: IssueIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """キーを発行する（BOOTHに登録して配布する用）。開発モード限定。"""
    if not get_settings().dev_mode:
        raise HTTPException(403, "キー発行は開発者専用機能です（開発モードで有効化）。")
    count = max(1, min(100, payload.count))
    licenses = service.issue_licenses(session, count, payload.booth_order_number)
    return {"count": len(licenses), "keys": [lic.key for lic in licenses]}
