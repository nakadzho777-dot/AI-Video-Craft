"""Anthropic Claude プロバイダー（APIキー）.

設計書要件: APIキー入力 / APIキー確認ページへのリンク。
Anthropic Messages API を httpx で直接叩く。
"""
from __future__ import annotations

import httpx

from ..base import (
    AIProvider,
    ChatMessage,
    ChatResult,
    ProviderInfo,
    ProviderKind,
)
from ..registry import register

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_KEY_HELP = "https://console.anthropic.com/settings/keys"

# キー未設定時のフォールバック（最新世代）
DEFAULT_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
]


@register
class ClaudeProvider(AIProvider):
    id = "claude"
    display_name = "Anthropic Claude"
    kind = ProviderKind.API_KEY

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            display_name=self.display_name,
            kind=self.kind,
            api_key_help_url=ANTHROPIC_KEY_HELP,
        )

    async def list_models(self) -> list[str]:
        if not self.api_key:
            return DEFAULT_MODELS
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ANTHROPIC_API_BASE}/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
        return [m["id"] for m in data.get("data", [])]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ANTHROPIC_API_BASE}/models", headers=self._headers()
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.7,
    ) -> ChatResult:
        if not self.api_key:
            raise RuntimeError("Claude APIキーが設定されていません。")

        # Anthropic は system を専用フィールドに分離する
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload: dict = {
            "model": model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": turns,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{ANTHROPIC_API_BASE}/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        # content は blocks の配列。text ブロックを連結する
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return ChatResult(text=text, model=model, provider=self.id, raw=data)
