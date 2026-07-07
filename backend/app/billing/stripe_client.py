"""Stripe API クライアント（httpx・form encoded）.

必要最小限のエンドポイントのみ実装する。
"""
from __future__ import annotations

import httpx

from ..config import get_settings

_API = "https://api.stripe.com/v1"


class StripeError(RuntimeError):
    pass


def _auth() -> dict[str, str]:
    key = get_settings().stripe_secret_key
    if not key:
        raise StripeError("Stripe が設定されていません（STRIPE_SECRET_KEY）")
    return {"Authorization": f"Bearer {key}"}


async def create_checkout_session(
    *,
    mode: str,               # "payment"（買い切り）| "subscription"
    price_id: str,
    customer_email: str,
    client_reference_id: str,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Checkout セッションを作成し、{id, url} を含む dict を返す。"""
    data = {
        "mode": mode,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": client_reference_id,
        "metadata[device_id]": client_reference_id,
        "metadata[plan]": plan,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if customer_email:
        data["customer_email"] = customer_email
    # サブスクは subscription 側にも metadata を載せて後続イベントで参照可能に
    if mode == "subscription":
        data["subscription_data[metadata][device_id]"] = client_reference_id
        data["subscription_data[metadata][plan]"] = plan

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_API}/checkout/sessions", headers=_auth(), data=data
        )
    if resp.status_code >= 400:
        raise StripeError(f"Stripe checkout 作成に失敗: {resp.text}")
    return resp.json()


async def get_checkout_session(session_id: str) -> dict:
    """Checkout セッションの現在状態を取得する（Webhookに頼らず決済確認する用）。"""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API}/checkout/sessions/{session_id}", headers=_auth()
        )
    if resp.status_code >= 400:
        raise StripeError(f"Stripe セッション取得に失敗: {resp.text}")
    return resp.json()


async def get_subscription(subscription_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_API}/subscriptions/{subscription_id}", headers=_auth()
        )
    if resp.status_code >= 400:
        raise StripeError(f"Stripe subscription 取得に失敗: {resp.text}")
    return resp.json()
