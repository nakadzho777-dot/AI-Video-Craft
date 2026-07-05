"""ライセンス発行・引き換え・端末管理.

- 発行(issue): 販売者がキーを作成し、BOOTHの商品に登録して配布する。
- 引き換え(redeem): 購入者がアカウントにキーを紐づけ、端末を登録する（最大2台）。
- 端末解除(release): PC変更時に登録を解除して再登録できるようにする。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..auth.security import new_license_key
from ..db.models import DeviceRegistration, License, User
from .clock import effective_now
from .keys import get_private_key, get_public_key
from .signing import LicenseSignatureError, sign_license, verify_license


class LicenseError(RuntimeError):
    """ライセンス操作のエラー（ユーザー向けメッセージ付き）。"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def issue_licenses(
    session: Session, count: int, booth_order_number: str | None = None
) -> list[License]:
    """ライセンスキーを count 個発行する（販売者/BOOTH配布用）。"""
    created: list[License] = []
    for _ in range(count):
        # 万一の衝突を避けて一意キーを確保
        key = new_license_key()
        while session.exec(select(License).where(License.key == key)).first():
            key = new_license_key()
        lic = License(key=key, source="booth", booth_order_number=booth_order_number)
        session.add(lic)
        created.append(lic)
    session.commit()
    for lic in created:
        session.refresh(lic)
    return created


def _devices(session: Session, license_id: int) -> list[DeviceRegistration]:
    return list(
        session.exec(
            select(DeviceRegistration).where(
                DeviceRegistration.license_id == license_id
            )
        )
    )


def redeem_license(
    session: Session,
    user: User,
    key: str,
    device_id: str,
    device_name: str = "",
) -> License:
    """キーをアカウントに引き換え、この端末を登録する。"""
    key = key.strip()
    lic = session.exec(select(License).where(License.key == key)).first()
    if not lic:
        raise LicenseError("ライセンスキーが見つかりません。入力をご確認ください。")

    # 所有者チェック
    if lic.redeemed_by_user_id is not None and lic.redeemed_by_user_id != user.id:
        raise LicenseError("このライセンスは別のアカウントで使用されています。")

    # 未引き換えなら、このアカウントに紐づける
    if lic.redeemed_by_user_id is None:
        lic.redeemed_by_user_id = user.id
        lic.redeemed_at = _utcnow()
        session.add(lic)
        session.commit()
        session.refresh(lic)

    _register_device(session, lic, device_id, device_name)
    return lic


def _register_device(
    session: Session, lic: License, device_id: str, device_name: str
) -> DeviceRegistration:
    devices = _devices(session, lic.id)
    existing = next((d for d in devices if d.device_id == device_id), None)
    if existing:
        return existing  # 同じ端末は再登録不要
    if len(devices) >= lic.max_devices:
        raise LicenseError(
            f"登録端末が上限（{lic.max_devices}台）に達しています。"
            "別のPCの登録を解除してから登録してください。"
        )
    reg = DeviceRegistration(
        license_id=lic.id, device_id=device_id, device_name=device_name
    )
    session.add(reg)
    session.commit()
    session.refresh(reg)
    return reg


def get_user_license(session: Session, user: User) -> License | None:
    return session.exec(
        select(License).where(License.redeemed_by_user_id == user.id)
    ).first()


def list_devices(session: Session, license_id: int) -> list[DeviceRegistration]:
    return _devices(session, license_id)


# ============================================================
# オフライン署名ライセンス（方式A）
# ============================================================


def sign_for_email(email: str, kind: str, days: int, *, dev_mode: bool) -> str:
    """メールに紐づく署名ライセンスを発行する（販売者の秘密鍵で署名）。

    kind="perpetual"（買い切り, 無期限）/ "subscription"（days 日間有効）。
    """
    priv = get_private_key(dev_mode)
    if not priv:
        raise LicenseError(
            "署名用の秘密鍵が設定されていません（AIVC_LICENSE_PRIVATE_KEY）。"
        )
    if kind not in ("perpetual", "subscription"):
        raise LicenseError("種別は perpetual か subscription を指定してください。")

    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + days * 86400 if kind == "subscription" else None
    payload = {
        "email": email.strip().lower(),
        "plan": "pro",
        "kind": kind,
        "iat": now,
        "exp": exp,
        "lid": secrets.token_hex(8),
    }
    return sign_license(priv, payload)


def activate_offline(session: Session, user: User, token: str) -> License:
    """署名ライセンスを検証し、アカウントに適用する（オフライン）。"""
    try:
        payload = verify_license(get_public_key(), token)
    except LicenseSignatureError as e:
        raise LicenseError(str(e)) from e

    email = str(payload.get("email", "")).strip().lower()
    if email != user.email.strip().lower():
        raise LicenseError(
            "このライセンスは別のメールアドレス用です。"
            "購入時のメールアドレスでログインしてください。"
        )
    if payload.get("plan") != "pro":
        raise LicenseError("対応していないライセンスです。")

    kind = payload.get("kind", "perpetual")
    exp_ts = payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None
    )
    if (
        kind == "subscription"
        and expires_at is not None
        and effective_now(session) > expires_at
    ):
        raise LicenseError("このライセンスは有効期限が切れています。更新版をご利用ください。")

    lid = str(payload.get("lid") or "")
    key = f"SIGNED-{lid}" if lid else f"SIGNED-{token[-16:]}"

    # 1アカウント1件の署名ライセンス（更新時は上書き）
    lic = session.exec(
        select(License).where(
            License.redeemed_by_user_id == user.id,
            License.source == "offline_signed",
        )
    ).first() or License(key=key)

    lic.key = key
    lic.source = "offline_signed"
    lic.plan = "pro"
    lic.kind = kind
    lic.expires_at = expires_at
    lic.bound_email = email
    lic.redeemed_by_user_id = user.id
    lic.redeemed_at = _utcnow()
    lic.signed_token = token  # 同じトークンをキャッシュ用にも保存
    session.add(lic)
    session.commit()
    session.refresh(lic)
    return lic


def release_device(session: Session, user: User, device_id: str) -> None:
    """自分のライセンスから端末登録を解除する。"""
    lic = get_user_license(session, user)
    if not lic:
        raise LicenseError("引き換え済みライセンスがありません。")
    reg = session.exec(
        select(DeviceRegistration).where(
            DeviceRegistration.license_id == lic.id,
            DeviceRegistration.device_id == device_id,
        )
    ).first()
    if not reg:
        raise LicenseError("その端末は登録されていません。")
    session.delete(reg)
    session.commit()
