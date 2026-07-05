"""ロギング設定.

エラー処理・ログを最初から組み込む方針に沿い、
コンソール + ファイル出力の基本ロガーを提供する。
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings

_configured = False


def setup_logging() -> None:
    """アプリ全体のロギングを初期化する（多重初期化は無視）。"""
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    log_file = settings.log_dir / "backend.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
