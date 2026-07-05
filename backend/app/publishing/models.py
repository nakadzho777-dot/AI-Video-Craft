"""投稿支援のデータモデル.

設計書「投稿支援」の生成対象を構造化する。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PublishPack(BaseModel):
    """各プラットフォーム向けの投稿テキスト一式。"""

    youtube_titles: list[str] = Field(
        default_factory=list, description="YouTubeタイトル候補（3〜5個）"
    )
    youtube_description: str = Field(default="", description="YouTube説明欄")
    hashtags: list[str] = Field(
        default_factory=list, description="ハッシュタグ（#付き）"
    )
    pinned_comment: str = Field(default="", description="固定コメント")
    booth_text: str = Field(default="", description="BOOTH紹介文")
    x_post: str = Field(default="", description="X（旧Twitter）投稿文")
    instagram_post: str = Field(default="", description="Instagram投稿文")
    tiktok_post: str = Field(default="", description="TikTok投稿文")


class PublishRequest(BaseModel):
    """投稿テキスト生成リクエスト。"""

    # topic か project_id のどちらかを指定（project_id 優先で企画を参照）。
    topic: str = ""
    notes: str = Field(default="", description="トーン・宣伝したい点など")

    provider: str | None = None
    model: str | None = None

    # 指定するとプロジェクトの企画を参照し、生成結果を保存する
    project_id: int | None = None


class PublishResponse(BaseModel):
    pack: PublishPack
    provider: str
    model: str
    saved_to_project: int | None = None
