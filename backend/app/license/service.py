"""ライセンス発行・有効化（PC/デバイス単位）.

- 発行(issue): 販売者がキー/署名を作成し配布する。
- 有効化(activate/redeem): 購入者が自分のPC(デバイス)にライセンスを紐づける。
署名(方式A) / Stripe(方式B) いずれも device_id に紐づく。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..auth.security import new_license_key
from ..db.models import License
from .clock import effective_now
from .keys import get_private_key, get_public_key
from .signing import LicenseSignatureError, sign_license, verify_license


class LicenseError(RuntimeError):
    """ライセンス操作のエラー（ユーザー向けメッセージ付き）。"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_device_license(session: Session, device_id: str) -> License | None:
    return session.exec(
        select(License).where(License.device_id == device_id)
    ).first()


def issue_licenses(session: Session, count: int) -> list[License]:
    """ライセンスキーを count 個発行する（販売者/ストア配布用・未紐づけ）。"""
    created: list[License] = []
    for _ in range(count):
        key = new_license_key()
        while session.exec(select(License).where(License.key == key)).first():
            key = new_license_key()
        lic = License(key=key, source="manual")
        session.add(lic)
        created.append(lic)
    session.commit()
    for lic in created:
        session.refresh(lic)
    return created


def redeem_license(session: Session, device_id: str, key: str) -> License:
    """事前発行キーを、このPC(デバイス)に紐づける。"""
    key = key.strip()
    lic = session.exec(select(License).where(License.key == key)).first()
    if not lic:
        raise LicenseError("ライセンスキーが見つかりません。入力をご確認ください。")
    if lic.device_id and lic.device_id != device_id:
        raise LicenseError("このライセンスは別のPCで使用されています。")
    lic.device_id = device_id
    lic.redeemed_at = _utcnow()
    session.add(lic)
    session.commit()
    session.refresh(lic)
    return lic


# ============================================================
# オフライン署名ライセンス（方式A）
# ============================================================


def sign_for_device(device_id: str, kind: str, days: int, *, dev_mode: bool) -> str:
    """PC(デバイスID)に紐づく署名ライセンスを発行する（販売者の秘密鍵で署名）。

    kind="perpetual"（買い切り, 無期限）/ "subscription"（days 日間有効）。
    """
    priv = get_private_key(dev_mode)
    if not priv:
        raise LicenseError(
            "署名用の秘密鍵が設定されていません（AIVC_LICENSE_PRIVATE_KEY）。"
        )
    if kind not in ("perpetual", "subscription"):
        raise LicenseError("種別は perpetual か subscription を指定してください。")
    if not device_id.strip():
        raise LicenseError("デバイスIDを指定してください。")

    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + days * 86400 if kind == "subscription" else None
    payload = {
        "device": device_id.strip(),
        "plan": "pro",
        "kind": kind,
        "iat": now,
        "exp": exp,
        "lid": secrets.token_hex(8),
    }
    return sign_license(priv, payload)


def activate_offline(session: Session, device_id: str, token: str) -> License:
    """署名ライセンスを検証し、このPCに適用する（オフライン）。"""
    try:
        payload = verify_license(get_public_key(), token)
    except LicenseSignatureError as e:
        raise LicenseError(str(e)) from e

    signed_device = str(payload.get("device", "")).strip()
    if signed_device != device_id.strip():
        raise LicenseError(
            "このライセンスは別のPC用です（購入時に登録したPCで有効化してください）。"
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

    # 1デバイス1件の署名ライセンス（更新時は上書き）
    lic = session.exec(
        select(License).where(
            License.device_id == device_id, License.source == "offline_signed"
        )
    ).first() or License(key=key)

    lic.key = key
    lic.source = "offline_signed"
    lic.plan = "pro"
    lic.kind = kind
    lic.expires_at = expires_at
    lic.device_id = device_id
    lic.redeemed_at = _utcnow()
    lic.signed_token = token  # 同じトークンをキャッシュ用にも保存
    session.add(lic)
    session.commit()
    session.refresh(lic)
    return lic
