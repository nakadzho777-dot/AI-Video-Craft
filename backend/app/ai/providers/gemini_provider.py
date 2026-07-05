"""Google Gemini プロバイダー（APIキー）.

設計書要件: APIキー入力 / APIキー確認ページへのリンク。
Generative Language API (v1beta) を httpx で直接叩く。
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

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_KEY_HELP = "https://aistudio.google.com/app/apikey"


@register
class GeminiProvider(AIProvider):
    id = "gemini"
    display_name = "Google Gemini"
    kind = ProviderKind.API_KEY

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            display_name=self.display_name,
            kind=self.kind,
            api_key_help_url=GEMINI_KEY_HELP,
        )

    async def list_models(self) -> list[str]:
        if not self.api_key:
            return ["gemini-1.5-flash", "gemini-1.5-pro"]
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{GEMINI_API_BASE}/models", params={"key": self.api_key}
            )
            resp.raise_for_status()
            data = resp.json()
        # "models/gemini-1.5-flash" -> "gemini-1.5-flash"
        return [m["name"].split("/", 1)[-1] for m in data.get("models", [])]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{GEMINI_API_BASE}/models", params={"key": self.api_key}
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
            raise RuntimeError("Gemini APIキーが設定されていません。")

        # system メッセージは system_instruction にまとめ、他は contents へ
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role != "system"
        ]
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_parts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n".join(system_parts)}]
            }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{GEMINI_API_BASE}/models/{model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return ChatResult(text=text, model=model, provider=self.id, raw=data)
