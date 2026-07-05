"""オフライン署名ライセンス（Ed25519）.

ライセンス = 署名付きトークン。販売者の秘密鍵で発行し、
アプリは埋め込んだ公開鍵で **オフライン検証** する。

トークン形式: AIVC1.<base64url(payload_json)>.<base64url(signature)>
payload: { email, plan, kind, iat, exp|null, lid }
  - kind: "perpetual"（買い切り）| "subscription"（サブスク）
  - exp : サブスクの失効UNIX秒。買い切りは null
"""
from __future__ import annotations

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PREFIX = "AIVC1"


class LicenseSignatureError(RuntimeError):
    """ライセンスの署名検証に失敗した。"""


# --- base64url ヘルパ ---
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# --- 鍵 ---
def generate_keypair() -> tuple[str, str]:
    """(秘密鍵b64url, 公開鍵b64url) を生成する。"""
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes_raw()
    pub_raw = priv.public_key().public_bytes_raw()
    return _b64e(priv_raw), _b64e(pub_raw)


def _load_private(priv_b64: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_b64d(priv_b64))


def _load_public(pub_b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64d(pub_b64))


# --- 署名 / 検証 ---
def sign_license(private_key_b64: str, payload: dict) -> str:
    """payload を秘密鍵で署名し、ライセンストークンを返す。"""
    priv = _load_private(private_key_b64)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_b64 = _b64e(body)
    signing_input = f"{PREFIX}.{body_b64}".encode("ascii")
    sig = priv.sign(signing_input)
    return f"{PREFIX}.{body_b64}.{_b64e(sig)}"


def verify_license(public_key_b64: str, token: str) -> dict:
    """トークンを公開鍵で検証し、payload(dict) を返す。失敗時は例外。"""
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenseSignatureError("ライセンスの形式が正しくありません")
    _, body_b64, sig_b64 = parts

    pub = _load_public(public_key_b64)
    signing_input = f"{PREFIX}.{body_b64}".encode("ascii")
    try:
        pub.verify(_b64d(sig_b64), signing_input)
    except (InvalidSignature, ValueError) as e:
        raise LicenseSignatureError("ライセンスの署名が無効です") from e

    try:
        return json.loads(_b64d(body_b64))
    except (ValueError, json.JSONDecodeError) as e:
        raise LicenseSignatureError("ライセンスの内容を読み取れません") from e
