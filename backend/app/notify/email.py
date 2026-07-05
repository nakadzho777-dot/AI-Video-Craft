"""SMTP メール送信（標準ライブラリのみ）.

外部依存なし。SMTP 設定が無ければ送信しない（呼び出し側でフォールバック）。
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)


def is_email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def send_email(to: str, subject: str, body: str) -> None:
    """SMTP でメールを送信する。設定が無ければ RuntimeError。"""
    s = get_settings()
    if not is_email_configured():
        raise RuntimeError("SMTP が設定されていません")

    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
        if s.smtp_use_tls:
            server.starttls()
        server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)
    logger.info("Sent notification email to %s", to)
