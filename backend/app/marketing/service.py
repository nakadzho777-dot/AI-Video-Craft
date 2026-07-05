"""宣伝記事 量産サービス.

キーワードを解決（指定 or AI案出し）し、各キーワードから記事を生成する。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError, extract_json
from ..logging_conf import get_logger
from .models import MAX_ARTICLES, Article, MarketingRequest
from .prompts import (
    ARTICLE_SYSTEM,
    KEYWORD_SYSTEM,
    build_article_prompt,
    build_keyword_prompt,
)

logger = get_logger(__name__)


class MarketingError(RuntimeError):
    """宣伝記事生成に失敗した。"""


class MarketingService:
    """宣伝記事を量産するユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def _ideate_keywords(
        self, req: MarketingRequest, *, model: str
    ) -> list[str]:
        messages = [
            ChatMessage(role="system", content=KEYWORD_SYSTEM),
            ChatMessage(
                role="user",
                content=build_keyword_prompt(req.topic, req.count, req.tone),
            ),
        ]
        result = await self.provider.chat(messages, model=model, temperature=0.9)
        try:
            data = extract_json(result.text)
        except JsonExtractError as e:
            raise MarketingError(f"キーワード案出しに失敗しました: {e}") from e
        keywords = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()]
        if not keywords:
            raise MarketingError("キーワードを生成できませんでした")
        return keywords

    async def _generate_article(
        self, req: MarketingRequest, keyword: str, *, model: str
    ) -> Article:
        messages = [
            ChatMessage(role="system", content=ARTICLE_SYSTEM),
            ChatMessage(
                role="user",
                content=build_article_prompt(req.topic, keyword, req.tone),
            ),
        ]
        result = await self.provider.chat(messages, model=model, temperature=0.8)
        data = extract_json(result.text)  # JsonExtractError は呼び出し側で扱う
        data.setdefault("target_keyword", keyword)
        return Article.model_validate(data)

    async def generate_batch(
        self, req: MarketingRequest, *, model: str
    ) -> list[Article]:
        # キーワード解決（指定 > AI案出し）
        keywords = [k.strip() for k in req.keywords if k.strip()]
        if not keywords:
            keywords = await self._ideate_keywords(req, model=model)
        keywords = keywords[:MAX_ARTICLES]

        articles: list[Article] = []
        for kw in keywords:
            try:
                articles.append(await self._generate_article(req, kw, model=model))
            except Exception as e:
                # 1本失敗しても量産は継続する（無効JSON・検証エラー等）
                logger.warning("記事生成をスキップ (%s): %s", kw, e)
        if not articles:
            raise MarketingError("記事を1本も生成できませんでした")
        return articles
