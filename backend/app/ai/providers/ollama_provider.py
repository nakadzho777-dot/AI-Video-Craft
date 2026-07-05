"""Ollama プロバイダー（ローカル）.

設計書要件: ダウンロードURL / モデル一覧 / モデルDL。
ローカルサーバ（既定 http://localhost:11434）に対して実際に疎通する。
"""
from __future__ import annotations

import httpx

from ...config import get_settings
from ..base import (
    AIProvider,
    ChatMessage,
    ChatResult,
    ProviderInfo,
    ProviderKind,
)
from ..registry import register

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


@register
class OllamaProvider(AIProvider):
    id = "ollama"
    display_name = "Ollama (ローカル)"
    kind = ProviderKind.LOCAL

    def __init__(self, *, api_key=None, base_url=None):
        super().__init__(api_key=api_key, base_url=base_url)
        self.base_url = base_url or get_settings().ollama_base_url

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            display_name=self.display_name,
            kind=self.kind,
            download_url=OLLAMA_DOWNLOAD_URL,
        )

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def pull_model(self, model: str) -> None:
        """モデルをダウンロードする（設計書のモデルDLボタン用）。"""
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": False},
            )
            resp.raise_for_status()

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> ChatResult:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        # ローカルモデルは初回ロード + CPU 推論で時間がかかるため長めに待つ。
        timeout = httpx.Timeout(600.0, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as e:
            raise RuntimeError(
                "Ollama の応答がタイムアウトしました。"
                "モデルが大きい/初回ロード中の可能性があります。"
                "軽量モデルを試すか、しばらく待って再実行してください。"
            ) from e
        except httpx.ConnectError as e:
            raise RuntimeError(
                "Ollama に接続できません。Ollama が起動しているか確認してください。"
            ) from e
        return ChatResult(
            text=data.get("message", {}).get("content", ""),
            model=model,
            provider=self.id,
            raw=data,
        )
