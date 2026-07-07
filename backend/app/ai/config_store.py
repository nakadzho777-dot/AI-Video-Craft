"""AI プロバイダー設定ストア.

APIキー / 既定プロバイダー / 既定モデルを保持する。
ローカルの JSON ファイル（data_dir/ai_config.json）に永続化し、
バックエンド再起動後も設定が残るようにする。
※ 現状は平文保存（ローカル専用の雛形）。将来は OS キーチェーン等へ差し替える。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)


def _config_path() -> Path:
    return get_settings().data_dir / "ai_config.json"


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
        self._save()

    def set_default_model(self, provider_id: str, model: str | None) -> None:
        self.get(provider_id).default_model = model
        self._save()

    def set_default_provider(self, provider_id: str) -> None:
        self.default_provider = provider_id
        self._save()

    # --- 永続化 ---
    def _save(self) -> None:
        try:
            path = _config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "default_provider": self.default_provider,
                "providers": {
                    pid: {
                        "api_key": c.api_key,
                        "base_url": c.base_url,
                        "default_model": c.default_model,
                    }
                    for pid, c in self.providers.items()
                },
            }
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # 保存失敗は致命的でない
            logger.warning("AI設定の保存に失敗しました: %s", e)

    def load(self) -> None:
        try:
            path = _config_path()
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            self.default_provider = data.get("default_provider", self.default_provider)
            for pid, c in (data.get("providers") or {}).items():
                self.providers[pid] = ProviderConfig(
                    api_key=c.get("api_key"),
                    base_url=c.get("base_url"),
                    default_model=c.get("default_model"),
                )
        except Exception as e:
            logger.warning("AI設定の読み込みに失敗しました: %s", e)


# アプリ全体で共有する単一ストア（起動時にディスクから復元）
ai_config = AIConfigStore()
ai_config.load()
