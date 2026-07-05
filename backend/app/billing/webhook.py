"""Stripe Webhook 署名検証（標準ライブラリ hmac）.

Stripe-Signature: t=<timestamp>,v1=<hex署名>
signed_payload = "<t>.<raw body>" を webhook secret で HMAC-SHA256 する。
"""
from __future__ import annotations

import hashlib
import hmac
import json


class WebhookVerifyError(RuntimeError):
    pass


def verify_and_parse(raw_body: bytes, sig_header: str, secret: str) -> dict:
    """署名を検証し、イベント JSON(dict) を返す。失敗時は例外。"""
    if not sig_header:
        raise WebhookVerifyError("署名ヘッダがありません")

    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        raise WebhookVerifyError("署名ヘッダの形式が不正です")

    signed_payload = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookVerifyError("署名が一致しません")

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as e:
        raise WebhookVerifyError("イベントJSONを解析できません") from e
