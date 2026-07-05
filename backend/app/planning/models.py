"""企画データモデル.

設計書「AI企画機能」の生成対象を構造化して表現する。
- タイトル / 動画構成(ショート・通常) / 尺配分 / 冒頭の掴み / CTA / サムネイル案
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VideoFormat = Literal["short", "long"]


class PlanSection(BaseModel):
    """動画構成の1セクション（尺配分を含む）。"""

    name: str = Field(description="セクション名（例: イントロ、本編、まとめ）")
    duration_sec: int = Field(description="このセクションの尺（秒）", ge=0)
    description: str = Field(description="このセクションで話す/見せる内容")


class VideoPlan(BaseModel):
    """AIが生成する動画企画。"""

    topic: str = Field(description="企画の元になったテーマ")
    format: VideoFormat = Field(description="short=ショート動画 / long=通常動画")
    titles: list[str] = Field(description="タイトル候補（3〜5個）", default_factory=list)
    target_duration_sec: int = Field(description="動画全体の目標尺（秒）", ge=0)
    hook: str = Field(description="冒頭の掴み（最初の数秒で視聴者を惹きつける一言）")
    sections: list[PlanSection] = Field(
        description="動画構成と尺配分", default_factory=list
    )
    cta: str = Field(description="CTA（視聴後に促す行動）")
    thumbnail_ideas: list[str] = Field(
        description="サムネイル案（2〜4個）", default_factory=list
    )

    @property
    def sections_total_sec(self) -> int:
        return sum(s.duration_sec for s in self.sections)


class PlanRequest(BaseModel):
    """企画生成リクエスト。"""

    topic: str = Field(description="動画のテーマ / 指示（例: このツールの紹介動画）")
    format: Literal["short", "long", "auto"] = "auto"
    # 目標尺（秒）。未指定なら format から妥当な既定値を使う。
    target_duration_sec: int | None = None
    # 追加の要望（トーン、対象視聴者など）
    notes: str = ""

    # AI 実行設定（未指定なら既定プロバイダー/モデル）
    provider: str | None = None
    model: str | None = None

    # 指定するとプロジェクトへ企画を保存する
    project_id: int | None = None


class PlanResponse(BaseModel):
    plan: VideoPlan
    provider: str
    model: str
    saved_to_project: int | None = None
