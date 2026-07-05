"""決済イベント → ライセンス自動発行/更新.

Stripe の Webhook イベントを受けて、アカウントの Pro ライセンスを
作成・更新・失効する（手作業の署名なしで自動発行）。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from ..db.models import License, User
from ..license.offline import issue_offline_token
from ..logging_conf import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _from_unix(ts: int | None) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def _get_stripe_license(session: Session, user_id: int) -> License | None:
    return session.exec(
        select(License).where(
            License.redeemed_by_user_id == user_id, License.source == "stripe"
        )
    ).first()


def _by_subscription(session: Session, sub_id: str) -> License | None:
    return session.exec(
        select(License).where(License.stripe_subscription_id == sub_id)
    ).first()


def issue_or_update(
    session: Session,
    user_id: int,
    *,
    kind: str,
    expires_at: datetime | None,
    subscription_id: str | None = None,
    customer_id: str | None = None,
) -> License:
    """ユーザーの Stripe ライセンスを作成/更新する（1アカウント1件）。"""
    lic = _get_stripe_license(session, user_id) or License(
        key=f"STRIPE-{secrets.token_hex(8)}"
    )
    lic.source = "stripe"
    lic.plan = "pro"
    lic.kind = kind
    lic.expires_at = expires_at
    lic.redeemed_by_user_id = user_id
    lic.redeemed_at = _utcnow()
    if subscription_id:
        lic.stripe_subscription_id = subscription_id
    if customer_id:
        lic.stripe_customer_id = customer_id
    session.add(lic)
    session.commit()
    session.refresh(lic)

    # A+Bハイブリッド: オフライン利用トークンも発行して保存
    user = session.get(User, user_id)
    if user:
        try:
            issue_offline_token(session, user, lic)
        except Exception as e:  # トークン発行失敗でも決済処理は成功扱い
            logger.warning("オフライントークン発行に失敗: %s", e)
    return lic


def handle_event(session: Session, event: dict) -> str:
    """Stripe イベントを処理する。処理内容の要約文字列を返す。"""
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or obj.get("metadata", {}).get(
            "user_id"
        )
        plan = obj.get("metadata", {}).get("plan", "perpetual")
        if not user_id:
            return "skip: user_id なし"
        user_id = int(user_id)
        customer_id = obj.get("customer")

        if obj.get("mode") == "subscription" or plan == "subscription":
            sub_id = obj.get("subscription")
            # 初回は即Pro化（暫定期限）。正確な期限は invoice.paid で更新。
            expires = _utcnow() + timedelta(days=31)
            issue_or_update(
                session, user_id, kind="subscription", expires_at=expires,
                subscription_id=sub_id, customer_id=customer_id,
            )
            return f"issued subscription for user {user_id}"
        else:
            issue_or_update(
                session, user_id, kind="perpetual", expires_at=None,
                customer_id=customer_id,
            )
            return f"issued perpetual for user {user_id}"

    if etype == "invoice.paid":
        sub_id = obj.get("subscription")
        lic = _by_subscription(session, sub_id) if sub_id else None
        if not lic:
            return "skip: 対象サブスクなし"
        # 請求期間の終了日を新しい失効日にする
        lines = obj.get("lines", {}).get("data", [])
        period_end = None
        if lines:
            period_end = _from_unix(lines[0].get("period", {}).get("end"))
        lic.expires_at = period_end or (_utcnow() + timedelta(days=31))
        session.add(lic)
        session.commit()
        user = session.get(User, lic.redeemed_by_user_id)
        if user:
            try:
                issue_offline_token(session, user, lic)  # 期限更新を反映
            except Exception as e:
                logger.warning("トークン再発行に失敗: %s", e)
        return f"renewed subscription {sub_id}"

    if etype == "customer.subscription.deleted":
        sub_id = obj.get("id")
        lic = _by_subscription(session, sub_id) if sub_id else None
        if not lic:
            return "skip: 対象サブスクなし"
        lic.expires_at = _utcnow()  # 即失効 → Free
        lic.signed_token = ""       # キャッシュ済みトークンも無効化（期限切れ扱い）
        session.add(lic)
        session.commit()
        return f"canceled subscription {sub_id}"

    return f"ignored: {etype}"
