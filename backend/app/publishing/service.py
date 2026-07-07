"""投稿テキスト生成サービス.

AIプロバイダーへプロンプトを投げ、応答 JSON を PublishPack へ構造化する。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .models import PublishPack, PublishRequest
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class PublishParseError(RuntimeError):
    """AI応答を投稿テキストとして解釈できなかった。"""


class PublishingService:
    """投稿テキスト生成のユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(
        self, req: PublishRequest, *, model: str, plan_summary: str = "",
        video_analysis: str = "",
    ) -> PublishPack:
        topic = req.topic.strip() or "（動画の内容に基づく）"
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_user_prompt(
                    topic, plan_summary, req.notes, video_analysis
                ),
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.8
            )
        except JsonExtractError as e:
            raise PublishParseError(str(e)) from e

        try:
            pack = PublishPack.model_validate(data)
        except Exception as e:
            logger.warning("Publish pack validation failed: %s", e)
            raise PublishParseError(f"投稿テキストの形式が不正です: {e}") from e
        return pack
