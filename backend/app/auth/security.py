"""パスワードハッシュ / トークン生成.

外部依存を避け、標準ライブラリ(hashlib.pbkdf2_hmac)でハッシュ化する。
形式: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_license_key() -> str:
    """BOOTH配布用のライセンスキーを生成する（例: AIVC-PRO-XXXX-XXXX-XXXX）。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 紛らわしい文字を除外
    groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "AIVC-PRO-" + "-".join(groups)
