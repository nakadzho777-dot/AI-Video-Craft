"""企画生成サービス.

AIプロバイダーへプロンプトを投げ、応答 JSON を VideoPlan へ構造化する。
プロバイダーは注入されるため、特定の実装に依存しない（テスト容易）。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .models import PlanRequest, VideoPlan
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class PlanParseError(RuntimeError):
    """AI応答を企画として解釈できなかった。"""


class PlanningService:
    """企画生成のユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(
        self, req: PlanRequest, *, model: str, previous: list[str] | None = None
    ) -> VideoPlan:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_user_prompt(req, previous)),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.8
            )
        except JsonExtractError as e:
            raise PlanParseError(str(e)) from e

        # topic が欠けていてもリクエスト値で補完する
        data.setdefault("topic", req.topic)
        try:
            plan = VideoPlan.model_validate(data)
        except Exception as e:
            logger.warning("Plan validation failed: %s", e)
            raise PlanParseError(f"企画の形式が不正です: {e}") from e
        return plan
