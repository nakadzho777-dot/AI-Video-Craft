"""編集提案サービス.

AIプロバイダーへプロンプトを投げ、応答 JSON を EditSuggestion へ構造化する。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError, extract_json
from ..logging_conf import get_logger
from .models import EditSuggestion, SuggestRequest
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class SuggestParseError(RuntimeError):
    """AI応答を編集提案として解釈できなかった。"""


class EditingSuggestService:
    """編集提案生成のユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def suggest(self, req: SuggestRequest, *, model: str) -> EditSuggestion:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_user_prompt(req)),
        ]
        result = await self.provider.chat(messages, model=model, temperature=0.7)

        try:
            data = extract_json(result.text)
        except JsonExtractError as e:
            raise SuggestParseError(str(e)) from e

        try:
            suggestion = EditSuggestion.model_validate(data)
        except Exception as e:
            logger.warning("Edit suggestion validation failed: %s", e)
            raise SuggestParseError(f"編集提案の形式が不正です: {e}") from e
        return suggestion
