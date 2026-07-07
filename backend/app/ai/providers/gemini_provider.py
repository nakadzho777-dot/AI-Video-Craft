"""Google Gemini プロバイダー（APIキー）.

設計書要件: APIキー入力 / APIキー確認ページへのリンク。
Generative Language API (v1beta) を httpx で直接叩く。
"""
from __future__ import annotations

import base64

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

# JSON生成が途中で切れないよう十分な上限を渡す（gemini-2.5系は思考トークンも
# ここに含まれるため、未指定だと MAX_TOKENS で本文が空になり時々失敗していた）
_MAX_OUTPUT_TOKENS = 8192


def _extract_text(data: dict) -> str:
    """Gemini応答から本文テキストを安全に取り出す.

    candidates が無い / parts が空 / MAX_TOKENS・SAFETY 等で本文が返らない、
    といったケースで KeyError/IndexError にならず、原因の分かる例外にする。
    """
    # 入力プロンプト自体がブロックされた場合
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise RuntimeError(
            f"入力内容が安全フィルタでブロックされました（{feedback['blockReason']}）。"
            "表現を変えてもう一度お試しください。"
        )

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("AIから応答が返りませんでした。もう一度お試しください。")

    cand = candidates[0]
    parts = ((cand.get("content") or {}).get("parts")) or []
    # 思考(thought)パートは除き、本文テキストのみ連結する
    text = "".join(
        p["text"]
        for p in parts
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    )
    if text.strip():
        return text

    # 本文が空 → finishReason から原因を示す
    reason = cand.get("finishReason") or "不明"
    if reason == "MAX_TOKENS":
        raise RuntimeError(
            "AIの応答が長くなりすぎて途中で切れました。"
            "テーマや要望を短くするか、もう一度お試しください。"
        )
    if reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"):
        raise RuntimeError(
            f"AIの応答が安全フィルタでブロックされました（{reason}）。"
            "内容を変えてお試しください。"
        )
    raise RuntimeError(
        f"AIから有効な応答が得られませんでした（finishReason={reason}）。"
        "もう一度お試しください。"
    )


@register
class GeminiProvider(AIProvider):
    id = "gemini"
    display_name = "Google Gemini"
    kind = ProviderKind.API_KEY
    supports_vision = True
    supports_image_gen = True

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
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": _MAX_OUTPUT_TOKENS,
            },
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
        text = _extract_text(data)
        return ChatResult(text=text, model=model, provider=self.id, raw=data)

    async def analyze_images(
        self, prompt: str, images: list[bytes], *, model: str
    ) -> str:
        if not self.api_key:
            raise RuntimeError("Gemini APIキーが設定されていません。")
        parts: list[dict] = [{"text": prompt}]
        for img in images:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(img).decode("ascii"),
                    }
                }
            )
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": _MAX_OUTPUT_TOKENS,
            },
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{GEMINI_API_BASE}/models/{model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return _extract_text(data)

    async def generate_image(self, prompt: str, *, model: str | None = None) -> bytes:
        """テキストから画像を生成して画像バイト列を返す（Gemini 画像生成モデル）。"""
        if not self.api_key:
            raise RuntimeError("Gemini APIキーが設定されていません。")
        img_model = model or "gemini-2.0-flash-preview-image-generation"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{GEMINI_API_BASE}/models/{img_model}:generateContent",
                params={"key": self.api_key},
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"画像生成に失敗しました: {resp.text[:200]}")
            data = resp.json()
        for cand in data.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise RuntimeError("画像が生成されませんでした（モデル未対応の可能性）。")
