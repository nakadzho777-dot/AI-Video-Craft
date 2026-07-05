"""OpenAI プロバイダー（APIキー）.

設計書要件: APIキー入力 / APIキー確認ページへのリンク。
外部 SDK 依存を避け httpx で REST を直接叩く実装。
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

OPENAI_API_BASE = "https://api.openai.com/v1"
OPENAI_KEY_HELP = "https://platform.openai.com/api-keys"


@register
class OpenAIProvider(AIProvider):
    id = "openai"
    display_name = "OpenAI"
    kind = ProviderKind.API_KEY

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            display_name=self.display_name,
            kind=self.kind,
            api_key_help_url=OPENAI_KEY_HELP,
        )

    async def list_models(self) -> list[str]:
        if not self.api_key:
            # 代表的な既定モデル（キー未設定時のフォールバック）
            return ["gpt-4o-mini", "gpt-4o"]
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{OPENAI_API_BASE}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return sorted(m["id"] for m in data.get("data", []))

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{OPENAI_API_BASE}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
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
            raise RuntimeError("OpenAI APIキーが設定されていません。")
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OPENAI_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return ChatResult(text=text, model=model, provider=self.id, raw=data)
