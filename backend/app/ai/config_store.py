"""AI プロバイダー設定ストア.

APIキー / 既定プロバイダー / 既定モデルを保持する。
雛形段階ではプロセス内メモリ + 任意で環境変数を初期値に採用。
将来は暗号化してローカル保存（OS キーチェーン等）へ差し替える。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import get_settings


@dataclass
class ProviderConfig:
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None


@dataclass
class AIConfigStore:
    default_provider: str = field(
        default_factory=lambda: get_settings().default_ai_provider
    )
    providers: dict[str, ProviderConfig] = field(default_factory=dict)

    def get(self, provider_id: str) -> ProviderConfig:
        return self.providers.setdefault(provider_id, ProviderConfig())

    def set_api_key(self, provider_id: str, api_key: str | None) -> None:
        self.get(provider_id).api_key = api_key

    def set_default_model(self, provider_id: str, model: str | None) -> None:
        self.get(provider_id).default_model = model


# アプリ全体で共有する単一ストア
ai_config = AIConfigStore()
