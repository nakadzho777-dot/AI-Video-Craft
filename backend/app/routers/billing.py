"""購入（ライセンス申請）API.

方式Aでは決済連携が無いため、買い手の「購入リクエスト」を販売者へ通知する。
SMTP が設定されていれば自動送信、未設定なら mailto フォールバック用の情報を返す。
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..auth.deps import get_current_user
from ..billing import service as billing_service
from ..billing.stripe_client import StripeError, create_checkout_session
from ..billing.webhook import WebhookVerifyError, verify_and_parse
from ..config import get_settings
from ..db.database import get_session
from ..db.models import User
from ..logging_conf import get_logger
from ..notify.email import is_email_configured, send_email

logger = get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

_PLAN_LABEL = {"perpetual": "買い切り（無期限）", "subscription": "サブスク（期間制）"}


class PurchaseRequestIn(BaseModel):
    plan: str = "perpetual"  # perpetual | subscription
    note: str = ""


class PurchaseRequestOut(BaseModel):
    sent: bool               # SMTPで自動送信できたか
    notify_email: str        # 販売者の宛先
    mailto: str              # 未送信時に買い手のメールソフトで開くURL


def _build_message(user: User, plan_label: str, note: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[AI VideoCraft] 購入リクエスト: {user.email}"
    body_lines = [
        "AI VideoCraft の購入リクエストが届きました。",
        "",
        f"購入者アカウント: {user.email}",
        f"ユーザー名: {user.username}",
        f"希望プラン: {plan_label}",
        f"日時: {now}",
    ]
    if note.strip():
        body_lines += ["", f"メッセージ: {note.strip()}"]
    body_lines += [
        "",
        "--- 販売者の対応 ---",
        "入金確認後、下記でライセンスを署名発行して返信してください:",
        f"  python scripts/keygen.py sign --email {user.email} --kind <perpetual|subscription>",
    ]
    return subject, "\n".join(body_lines)


@router.post("/purchase-request", response_model=PurchaseRequestOut)
def purchase_request(
    payload: PurchaseRequestIn, user: User = Depends(get_current_user)
) -> PurchaseRequestOut:
    settings = get_settings()
    to = settings.notify_email
    plan_label = _PLAN_LABEL.get(payload.plan, payload.plan)
    subject, body = _build_message(user, plan_label, payload.note)

    # mailto フォールバック（常に用意する）
    mailto = f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"

    sent = False
    if is_email_configured():
        try:
            send_email(to, subject, body)
            sent = True
        except Exception as e:  # 送信失敗時は mailto にフォールバック
            logger.warning("購入通知メールの送信に失敗しました: %s", e)

    return PurchaseRequestOut(sent=sent, notify_email=to, mailto=mailto)


# ============================================================
# 方式B: Stripe 決済で自動発行
# ============================================================


class CheckoutIn(BaseModel):
    plan: str = "perpetual"  # perpetual | subscription


@router.get("/config")
def billing_config() -> dict:
    """フロント向け: 決済が有効か、どのプランが購入可能か。"""
    s = get_settings()
    return {
        "stripe_enabled": s.stripe_enabled(),
        "perpetual_available": bool(s.stripe_price_perpetual),
        "subscription_available": bool(s.stripe_price_subscription),
    }


@router.post("/checkout")
async def checkout(
    payload: CheckoutIn, user: User = Depends(get_current_user)
) -> dict:
    """Stripe Checkout セッションを作成し、決済URLを返す。"""
    s = get_settings()
    if not s.stripe_enabled():
        raise HTTPException(400, "決済（Stripe）が設定されていません。")
    price_id = s.stripe_price_for(payload.plan)
    if not price_id:
        raise HTTPException(400, f"プラン '{payload.plan}' の価格が未設定です。")

    mode = "subscription" if payload.plan == "subscription" else "payment"
    try:
        sess = await create_checkout_session(
            mode=mode,
            price_id=price_id,
            customer_email=user.email,
            client_reference_id=str(user.id),
            plan=payload.plan,
            success_url=s.billing_success_url,
            cancel_url=s.billing_cancel_url,
        )
    except StripeError as e:
        raise HTTPException(502, str(e)) from e
    return {"checkout_url": sess.get("url"), "session_id": sess.get("id")}


@router.post("/webhook")
async def stripe_webhook(
    request: Request, session: Session = Depends(get_session)
) -> dict:
    """Stripe からの Webhook を受けてライセンスを自動発行する。"""
    s = get_settings()
    if not s.stripe_webhook_secret:
        raise HTTPException(400, "Webhook secret が未設定です。")

    raw = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = verify_and_parse(raw, sig, s.stripe_webhook_secret)
    except WebhookVerifyError as e:
        raise HTTPException(400, f"Webhook 検証失敗: {e}") from e

    try:
        result = billing_service.handle_event(session, event)
    except Exception as e:  # 予期せぬ処理エラーでも 500 を返さない（再送地獄回避）
        logger.exception("webhook 処理エラー")
        return {"received": True, "error": str(e)}
    logger.info("stripe webhook: %s -> %s", event.get("type"), result)
    return {"received": True, "result": result}
