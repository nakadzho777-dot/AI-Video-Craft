"""購入（ライセンス申請）API.

方式Aでは決済連携が無いため、買い手の「購入リクエスト」を販売者へ通知する。
SMTP が設定されていれば自動送信、未設定なら mailto フォールバック用の情報を返す。
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session

from ..billing import service as billing_service
from ..billing.stripe_client import (
    StripeError,
    create_checkout_session,
    get_checkout_session,
)
from ..billing.webhook import WebhookVerifyError, verify_and_parse
from ..license.manager import plan_for_device
from ..config import get_settings
from ..db.database import get_session
from ..deps import get_device_id
from ..logging_conf import get_logger
from ..notify.email import is_email_configured, send_email

logger = get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

_PLAN_LABEL = {"perpetual": "買い切り（無期限）", "subscription": "サブスク（期間制）"}


class PurchaseRequestIn(BaseModel):
    plan: str = "perpetual"  # perpetual | subscription
    contact: str = ""        # 買い手の連絡先（返信用・任意）
    note: str = ""


class PurchaseRequestOut(BaseModel):
    sent: bool               # SMTPで自動送信できたか
    notify_email: str        # 販売者の宛先
    mailto: str              # 未送信時に買い手のメールソフトで開くURL


def _build_message(
    device_id: str, contact: str, plan_label: str, note: str
) -> tuple[str, str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[AI VideoCraft] 購入リクエスト: {device_id[:12]}"
    body_lines = [
        "AI VideoCraft の購入リクエストが届きました。",
        "",
        f"デバイスID: {device_id}",
        f"連絡先: {contact or '(未記入)'}",
        f"希望プラン: {plan_label}",
        f"日時: {now}",
    ]
    if note.strip():
        body_lines += ["", f"メッセージ: {note.strip()}"]
    body_lines += [
        "",
        "--- 販売者の対応 ---",
        "入金確認後、下記でライセンスを署名発行して返信してください:",
        f"  python scripts/keygen.py sign --device {device_id} "
        "--kind <perpetual|subscription>",
    ]
    return subject, "\n".join(body_lines)


@router.post("/purchase-request", response_model=PurchaseRequestOut)
def purchase_request(
    payload: PurchaseRequestIn, device_id: str = Depends(get_device_id)
) -> PurchaseRequestOut:
    settings = get_settings()
    to = settings.notify_email
    plan_label = _PLAN_LABEL.get(payload.plan, payload.plan)
    subject, body = _build_message(
        device_id, payload.contact, plan_label, payload.note
    )

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
    payload: CheckoutIn,
    request: Request,
    device_id: str = Depends(get_device_id),
) -> dict:
    """Stripe Checkout セッションを作成し、決済URLを返す。"""
    s = get_settings()
    if not s.stripe_enabled():
        raise HTTPException(400, "決済（Stripe）が設定されていません。")
    price_id = s.stripe_price_for(payload.plan)
    if not price_id:
        raise HTTPException(400, f"プラン '{payload.plan}' の価格が未設定です。")

    # リダイレクト先: 設定があればそれを、無ければバックエンド自身の案内ページ
    base = str(request.base_url).rstrip("/")
    success_url = s.billing_success_url or f"{base}/billing/success"
    cancel_url = s.billing_cancel_url or f"{base}/billing/cancel"

    mode = "subscription" if payload.plan == "subscription" else "payment"
    try:
        sess = await create_checkout_session(
            mode=mode,
            price_id=price_id,
            customer_email="",  # メールはStripe側で収集
            client_reference_id=device_id,
            plan=payload.plan,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except StripeError as e:
        raise HTTPException(502, str(e)) from e
    return {"checkout_url": sess.get("url"), "session_id": sess.get("id")}


# ============================================================
# 決済後の案内ページ（ブラウザに表示。アプリ側はポーリングでPro反映）
# ============================================================
def _result_page(title: str, emoji: str, message: str, accent: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - AI VideoCraft</title>
<style>
  html,body{{height:100%;margin:0}}
  body{{display:flex;align-items:center;justify-content:center;
    font-family:"Segoe UI","Meiryo",system-ui,sans-serif;
    background:#0b0b18;color:#e9e9f2}}
  .card{{max-width:460px;padding:40px 36px;text-align:center;
    background:#15152a;border:1px solid #2a2a44;border-radius:20px;
    box-shadow:0 20px 60px rgba(0,0,0,.45)}}
  .emoji{{font-size:60px;line-height:1}}
  h1{{margin:18px 0 8px;font-size:24px;color:{accent}}}
  p{{margin:6px 0;color:#b9b9cc;line-height:1.7}}
  .hint{{margin-top:22px;font-size:13px;color:#8a8aa3}}
</style></head>
<body><div class="card">
  <div class="emoji">{emoji}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <p class="hint">このタブは閉じて、AI VideoCraft に戻ってください。</p>
</div>
<script>setTimeout(function(){{try{{window.close()}}catch(e){{}}}},1200);</script>
</body></html>"""
    return HTMLResponse(html)


@router.get("/success", response_class=HTMLResponse)
def checkout_success() -> HTMLResponse:
    return _result_page(
        "決済が完了しました",
        "✅",
        "ご購入ありがとうございます。アプリに戻ると自動的にPro版が有効になります。",
        "#4ade80",
    )


@router.get("/cancel", response_class=HTMLResponse)
def checkout_cancel() -> HTMLResponse:
    return _result_page(
        "決済をキャンセルしました",
        "↩️",
        "決済は行われていません。アプリからいつでもやり直せます。",
        "#facc15",
    )


class VerifyIn(BaseModel):
    session_id: str


@router.post("/verify")
async def verify_checkout(
    payload: VerifyIn,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> dict:
    """session_id で決済状況を Stripe に直接確認し、支払い済みなら Pro を発行する。

    デスクトップ版は Stripe Webhook を受けられない（公開URLが無い）ため、
    アプリがポーリングでこのAPIを叩き、Webhookなしでも Pro 化できるようにする。
    """
    s = get_settings()
    if not s.stripe_enabled():
        raise HTTPException(400, "決済（Stripe）が設定されていません。")
    if not payload.session_id.strip():
        raise HTTPException(400, "session_id が必要です。")

    try:
        obj = await get_checkout_session(payload.session_id.strip())
    except StripeError as e:
        raise HTTPException(502, str(e)) from e

    # 他人のセッションで有効化されないよう、購入時のデバイスと一致を確認
    ref = obj.get("client_reference_id") or (obj.get("metadata") or {}).get(
        "device_id"
    )
    if ref and ref != device_id:
        raise HTTPException(403, "このPCで開始した決済ではありません。")

    paid = obj.get("payment_status") == "paid" or obj.get("status") == "complete"
    activated = False
    if paid:
        # Webhook と同じ処理でライセンスを発行/更新（冪等：1デバイス1件を更新）
        billing_service.handle_event(
            session, {"type": "checkout.session.completed", "data": {"object": obj}}
        )
        activated = True

    return {
        "paid": paid,
        "activated": activated,
        "plan": plan_for_device(device_id, session).value,
    }


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
