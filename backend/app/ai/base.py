"""AI プロバイダー共通インターフェース.

設計方針: 「AIプロバイダーを追加しやすい構造」。
新しいプロバイダーは AIProvider を継承し、registry.register で登録するだけ。
UI やビジネスロジックは具体的なプロバイダーに依存しない。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class ProviderKind(str, Enum):
    """設定 UI の出し分けに使う種別。"""

    LOCAL = "local"    # Ollama など（ダウンロードURL / モデル一覧）
    API_KEY = "apikey"  # OpenAI / Gemini / Claude（APIキー入力）


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResult:
    text: str
    model: str
    provider: str
    raw: dict = field(default_factory=dict)


@dataclass
class ProviderInfo:
    """設定画面へ渡すメタ情報。"""

    id: str
    display_name: str
    kind: ProviderKind
    # LOCAL 用
    download_url: str | None = None
    # API_KEY 用
    api_key_help_url: str | None = None


class AIProvider(abc.ABC):
    """全 AI プロバイダーが実装するインターフェース。"""

    #: 一意な識別子（"ollama", "openai" など）
    id: str = ""
    #: 設定画面に出す表示名
    display_name: str = ""
    #: 種別（設定 UI 出し分け用）
    kind: ProviderKind = ProviderKind.API_KEY

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    # --- メタ情報 ---
    @abc.abstractmethod
    def info(self) -> ProviderInfo:
        """設定 UI 向けメタ情報を返す。"""

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        """利用可能なモデル一覧を返す。"""

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """接続確認（APIキー検証 / ローカルサーバ疎通など）。"""

    # --- 生成 ---
    @abc.abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> ChatResult:
        """チャット補完を実行する。"""
