"""録画ガイド生成サービス.

AIプロバイダーへプロンプトを投げ、応答 JSON を RecordingGuide へ構造化する。
プロバイダーは注入されるため、特定実装に依存しない（テスト容易）。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .models import GuideRequest, RecordingGuide
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class GuideParseError(RuntimeError):
    """AI応答を録画ガイドとして解釈できなかった。"""


class RecordingGuideService:
    """録画ガイド生成のユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(
        self, req: GuideRequest, *, model: str, plan_summary: str = ""
    ) -> RecordingGuide:
        topic = req.topic.strip() or "（企画に基づく動画）"
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_user_prompt(topic, plan_summary, req.notes),
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.6
            )
        except JsonExtractError as e:
            raise GuideParseError(str(e)) from e

        data.setdefault("topic", topic)
        try:
            guide = RecordingGuide.model_validate(data)
        except Exception as e:
            logger.warning("Guide validation failed: %s", e)
            raise GuideParseError(f"録画ガイドの形式が不正です: {e}") from e

        if not guide.steps:
            raise GuideParseError("ステップが生成されませんでした")
        return guide
