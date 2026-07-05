"""ライセンス署名鍵の解決.

公開鍵: 検証に使う。アプリに埋め込む（環境変数で上書き可）。
秘密鍵: 発行(署名)に使う。**販売者のみ**が環境変数で設定する。配布物には入れない。

同梱の DEV 鍵は「すぐ試せる」ためのもので、私的な開発/デモ専用。
実販売の前に必ず `keygen.py init` で自分の鍵に差し替えてください
（環境変数 AIVC_LICENSE_PUBLIC_KEY / AIVC_LICENSE_PRIVATE_KEY）。
"""
from __future__ import annotations

import os

# --- 同梱DEV鍵（デモ専用・実販売では差し替える）---
_DEV_PUBLIC_KEY = "493hT-FNwLPTA7008x5C-WfEbkbjKCoG-sn8sg4BRKI"
# DEV秘密鍵は dev_mode かつ環境変数未設定のときだけフォールバックとして使う。
_DEV_PRIVATE_KEY = "jklv_cc4csO4bhycJ2y8q2-wThMJNhoe29TyytDgrag"


def get_public_key() -> str:
    """検証用の公開鍵（b64url）。環境変数優先、無ければ同梱DEV鍵。"""
    return os.environ.get("AIVC_LICENSE_PUBLIC_KEY", _DEV_PUBLIC_KEY)


def get_private_key(dev_mode: bool = False) -> str | None:
    """署名用の秘密鍵（b64url）。

    環境変数 AIVC_LICENSE_PRIVATE_KEY があればそれを使う。
    無い場合は、開発モードのときだけ同梱DEV鍵で署名を許可する。
    本番（dev_mode=False かつ未設定）では None（署名不可）。
    """
    key = os.environ.get("AIVC_LICENSE_PRIVATE_KEY")
    if key:
        return key
    return _DEV_PRIVATE_KEY if dev_mode else None


def is_dev_signing_key() -> bool:
    """署名(秘密)鍵が同梱DEV鍵かどうか（UIの警告表示用）。"""
    return "AIVC_LICENSE_PRIVATE_KEY" not in os.environ


def is_dev_public_key() -> bool:
    """検証(公開)鍵が同梱DEV鍵かどうか（実販売前の警告表示用）。"""
    return get_public_key() == _DEV_PUBLIC_KEY
