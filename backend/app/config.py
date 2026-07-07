"""アプリケーション設定管理.

設定は環境変数 / .env ファイルから読み込む。
将来的な設定項目の追加はこのクラスにフィールドを足すだけで済む。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ ディレクトリ（このファイルの2つ上）を基準にする
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """全体設定。環境変数プレフィックスは AIVC_。"""

    model_config = SettingsConfigDict(
        env_prefix="AIVC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- サーバ ---
    host: str = "127.0.0.1"
    port: int = 8756

    # --- データ / DB ---
    data_dir: Path = DATA_DIR
    db_path: Path = DATA_DIR / "videocraft.sqlite3"

    # --- ログ ---
    log_level: str = "INFO"
    log_dir: Path = BASE_DIR / "logs"

    # --- 動画処理 ---
    ffmpeg_path: str = "ffmpeg"  # PATH 上にある想定。フルパスも指定可

    # --- AI 既定プロバイダー ---
    default_ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"

    # --- ゆっくり解説: AquesTalk（本物のゆっくり声）---
    # AquesTalk.dll 等を置いたフォルダ。未設定なら edge-tts を使う。
    # 販売アプリで商用利用するには AquesTalk の商用ライセンスが必要。
    aquestalk_dir: str = ""

    # --- 音声: VOICEVOX（無料・商用可・多数のキャラ声）---
    # VOICEVOX エンジンの URL。エンジンを起動していれば多数の声が使える。
    # localhost だと IPv6(::1) 解決で遅くなるため 127.0.0.1 を既定にする。
    voicevox_url: str = "http://127.0.0.1:50021"

    # --- 開発者モード ---
    # 開発者(自分)専用機能（宣伝AI: 記事/SEO量産）の有効化。
    # 既定は無効。AIVC_DEV_MODE=1 で有効化する。エンドユーザーには公開しない。
    dev_mode: bool = False

    # --- 購入通知メール ---
    # 通知の宛先（販売者）。購入リクエスト時にここへメールが届く。
    notify_email: str = "nakadzho777@gmail.com"
    # SMTP（設定されていれば自動送信、未設定なら mailto フォールバック）
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""          # 空なら smtp_user を使う
    smtp_use_tls: bool = True

    # --- 決済（方式B: Stripe 自動発行）---
    # すべて未設定なら決済機能は無効（購入リクエスト=方式Aのみ）。
    stripe_secret_key: str = ""            # sk_test_... / sk_live_...
    stripe_webhook_secret: str = ""        # whsec_...
    stripe_price_perpetual: str = ""       # 買い切り用 price_...（mode=payment）
    stripe_price_subscription: str = ""    # サブスク用 price_...（mode=subscription）
    # チェックアウト後のリダイレクト先。空ならバックエンド自身の案内ページ
    # (/billing/success, /billing/cancel) を自動で使う。
    billing_success_url: str = ""
    billing_cancel_url: str = ""

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def stripe_enabled(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    def stripe_price_for(self, plan: str) -> str | None:
        return {
            "perpetual": self.stripe_price_perpetual,
            "subscription": self.stripe_price_subscription,
        }.get(plan) or None

    def ensure_dirs(self) -> None:
        """必要なディレクトリを作成する。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """設定のシングルトン取得。"""
    settings = Settings()
    settings.ensure_dirs()
    return settings
