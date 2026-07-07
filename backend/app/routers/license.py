"""ライセンス API（PC/デバイス単位）.

- GET  /license/status          : このPCのライセンス・プラン
- POST /license/redeem          : 事前発行キーをこのPCで有効化
- POST /license/activate-offline: 署名ライセンス（オフライン）をこのPCで有効化
- GET  /license/offline-token   : オフライン利用トークン（A+Bハイブリッド）
- POST /license/sign            : デバイスIDに紐づく署名発行（販売者・dev_mode）
- POST /license/issue / keygen / signing-info : 販売者向け（dev_mode）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..config import get_settings
from ..db.database import get_session
from ..deps import get_device_id
from ..license import service
from ..license.keys import is_dev_public_key, is_dev_signing_key
from ..license.manager import license_is_active, plan_for_device
from ..license.offline import issue_offline_token
from ..license.signing import generate_keypair

router = APIRouter(prefix="/license", tags=["license"])


class RedeemIn(BaseModel):
    license_key: str


class ActivateOfflineIn(BaseModel):
    license_token: str


class SignIn(BaseModel):
    device_id: str
    kind: str = "perpetual"       # perpetual | subscription
    days: int = 365               # subscription の有効日数


class IssueIn(BaseModel):
    count: int = 1


class LicenseStatusOut(BaseModel):
    plan: str
    device_id: str
    has_license: bool
    license_key: str | None = None
    source: str | None = None
    kind: str | None = None
    expires_at: str | None = None


def _status(session: Session, device_id: str) -> LicenseStatusOut:
    lic = service.get_device_license(session, device_id)
    plan = plan_for_device(device_id, session).value
    if not lic:
        return LicenseStatusOut(plan=plan, device_id=device_id, has_license=False)
    return LicenseStatusOut(
        plan=plan,
        device_id=device_id,
        has_license=True,
        license_key=lic.key,
        source=lic.source,
        kind=lic.kind,
        expires_at=lic.expires_at.isoformat() if lic.expires_at else None,
    )


@router.get("/status", response_model=LicenseStatusOut)
def status_(
    device_id: str = Depends(get_device_id),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    return _status(session, device_id)


@router.post("/redeem", response_model=LicenseStatusOut)
def redeem(
    payload: RedeemIn,
    device_id: str = Depends(get_device_id),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    try:
        service.redeem_license(session, device_id, payload.license_key)
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return _status(session, device_id)


@router.post("/activate-offline", response_model=LicenseStatusOut)
def activate_offline(
    payload: ActivateOfflineIn,
    device_id: str = Depends(get_device_id),
    session: Session = Depends(get_session),
) -> LicenseStatusOut:
    """署名ライセンス（オフライン）をこのPCで有効化する。"""
    try:
        service.activate_offline(session, device_id, payload.license_token)
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return _status(session, device_id)


@router.get("/offline-token")
def offline_token(
    device_id: str = Depends(get_device_id),
    session: Session = Depends(get_session),
) -> dict:
    """オフライン利用トークンを返す（A+Bハイブリッド）。"""
    lic = service.get_device_license(session, device_id)
    if not lic or not license_is_active(lic, session):
        return {"token": None}
    token = lic.signed_token or issue_offline_token(session, device_id, lic)
    return {"token": token}


@router.post("/sign")
def sign(payload: SignIn, session: Session = Depends(get_session)) -> dict:
    """デバイスIDに紐づく署名ライセンスを発行する（販売者用）。開発モード限定。"""
    dev = get_settings().dev_mode
    if not dev:
        raise HTTPException(403, "署名発行は販売者専用機能です（開発モードで有効化）。")
    try:
        token = service.sign_for_device(
            payload.device_id, payload.kind, payload.days, dev_mode=dev
        )
    except service.LicenseError as e:
        raise HTTPException(400, str(e)) from e
    return {"license_token": token, "device_id": payload.device_id.strip()}


@router.get("/signing-info")
def signing_info() -> dict:
    """署名鍵の状態（実販売前の差し替え警告用）。開発モード限定。"""
    if not get_settings().dev_mode:
        raise HTTPException(403, "開発者専用機能です。")
    return {
        "using_dev_public_key": is_dev_public_key(),
        "using_dev_private_key": is_dev_signing_key(),
    }


@router.post("/keygen")
def keygen() -> dict:
    """本番用の鍵ペアを生成する（表示のみ・保存しない）。開発モード限定。"""
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
def issue(payload: IssueIn, session: Session = Depends(get_session)) -> dict:
    """未紐づけキーを発行する（ストア配布用）。開発モード限定。"""
    if not get_settings().dev_mode:
        raise HTTPException(403, "キー発行は開発者専用機能です（開発モードで有効化）。")
    count = max(1, min(100, payload.count))
    licenses = service.issue_licenses(session, count)
    return {"count": len(licenses), "keys": [lic.key for lic in licenses]}
