"""共通の依存性.

アカウント(ログイン)を廃止し、PC(デバイス)単位で管理する。
各リクエストは X-Device-Id ヘッダでデバイスを識別する。
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status


def get_device_id(x_device_id: str | None = Header(default=None)) -> str:
    """リクエストヘッダからデバイスIDを取得する（必須）。"""
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "デバイスIDがありません（X-Device-Id ヘッダが必要です）。",
        )
    return x_device_id.strip()
