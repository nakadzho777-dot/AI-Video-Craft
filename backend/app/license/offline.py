"""オフライン利用トークンの発行（A+Bハイブリッド）.

Pro ライセンスに対し、サーバが署名したトークンを発行して保存する。
アプリはこれをキャッシュし、バックエンドに接続できないときも
埋め込んだ公開鍵で検証して Pro 状態を維持できる。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlmodel import Session

from ..config import get_settings
from ..db.models import License, User
from ..logging_conf import get_logger
from .keys import get_private_key
from .signing import sign_license

logger = get_logger(__name__)


def issue_offline_token(session: Session, user: User, lic: License) -> str | None:
    """ライセンスに紐づく署名トークンを発行し保存する。

    秘密鍵が無い環境（配布ビルド）では None（発行しない）。
    exp はサブスクの失効日時、買い切りは無期限。
    """
    priv = get_private_key(get_settings().dev_mode)
    if not priv:
        return None

    exp = None
    if lic.kind == "subscription" and lic.expires_at is not None:
        e = lic.expires_at
        if e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        exp = int(e.timestamp())

    payload = {
        "email": user.email.strip().lower(),
        "plan": "pro",
        "kind": lic.kind,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": exp,
        "lid": secrets.token_hex(8),
    }
    token = sign_license(priv, payload)
    lic.signed_token = token
    session.add(lic)
    session.commit()
    return token
