"""宣伝AIのデータモデル.

SEO最適化された宣伝記事を量産するための構造。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# 一度に生成する記事数の上限（暴走防止）
MAX_ARTICLES = 10


class Article(BaseModel):
    """SEO宣伝記事1本。"""

    title: str = Field(description="記事タイトル（SEO最適化）")
    slug: str = Field(default="", description="URLスラッグ（半角英数ハイフン）")
    target_keyword: str = Field(default="", description="狙う主要キーワード")
    meta_description: str = Field(
        default="", description="メタディスクリプション（120字程度）"
    )
    keywords: list[str] = Field(default_factory=list, description="関連キーワード")
    outline: list[str] = Field(
        default_factory=list, description="見出し構成（H2/H3）"
    )
    body_markdown: str = Field(default="", description="本文（Markdown）")


class MarketingRequest(BaseModel):
    """宣伝記事の量産リクエスト。"""

    topic: str = Field(description="宣伝対象（製品名・サービス・動画テーマ）")
    # キーワード指定時は各キーワードで1記事ずつ生成する。
    keywords: list[str] = Field(default_factory=list)
    # キーワード未指定時に生成する記事数。
    count: int = Field(default=3, ge=1, le=MAX_ARTICLES)
    tone: str = Field(default="", description="トーン・ターゲット読者など")

    provider: str | None = None
    model: str | None = None


class MarketingResponse(BaseModel):
    articles: list[Article]
    provider: str
    model: str
    requested: int
    generated: int
