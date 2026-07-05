"""オフライン署名ライセンス keygen（販売者用）.

使い方:
  # 1回だけ: 鍵ペアを生成
  python scripts/keygen.py init

  # 購入のたび: メールに紐づくライセンスを署名発行
  #   秘密鍵は環境変数 AIVC_LICENSE_PRIVATE_KEY に設定しておく
  python scripts/keygen.py sign --email buyer@example.com --kind perpetual
  python scripts/keygen.py sign --email buyer@example.com --kind subscription --days 365

秘密鍵はこの端末だけに保管し、配布物やリポジトリには絶対に入れないこと。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# backend ルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.license.signing import generate_keypair, sign_license  # noqa: E402


def cmd_init() -> None:
    priv, pub = generate_keypair()
    print("鍵ペアを生成しました。安全に保管してください。\n")
    print("--- 公開鍵（アプリに埋め込む / 環境変数） ---")
    print(f"AIVC_LICENSE_PUBLIC_KEY={pub}\n")
    print("--- 秘密鍵（あなたの端末だけに保管・絶対に配布しない） ---")
    print(f"AIVC_LICENSE_PRIVATE_KEY={priv}\n")
    print("配布アプリ側には公開鍵を、署名する端末には秘密鍵を設定してください。")


def cmd_sign(args: argparse.Namespace) -> None:
    import secrets
    from datetime import datetime, timezone

    priv = os.environ.get("AIVC_LICENSE_PRIVATE_KEY")
    if not priv:
        sys.exit("環境変数 AIVC_LICENSE_PRIVATE_KEY を設定してください（init で生成）。")
    if args.kind not in ("perpetual", "subscription"):
        sys.exit("--kind は perpetual か subscription を指定してください。")

    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + args.days * 86400 if args.kind == "subscription" else None
    payload = {
        "email": args.email.strip().lower(),
        "plan": "pro",
        "kind": args.kind,
        "iat": now,
        "exp": exp,
        "lid": secrets.token_hex(8),
    }
    token = sign_license(priv, payload)
    print(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI VideoCraft ライセンス署名ツール")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="鍵ペアを生成する")
    sp = sub.add_parser("sign", help="ライセンスを署名発行する")
    sp.add_argument("--email", required=True, help="購入者のメールアドレス")
    sp.add_argument(
        "--kind", default="perpetual", help="perpetual（買い切り）/ subscription"
    )
    sp.add_argument("--days", type=int, default=365, help="サブスクの有効日数")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init()
    elif args.command == "sign":
        cmd_sign(args)


if __name__ == "__main__":
    main()
