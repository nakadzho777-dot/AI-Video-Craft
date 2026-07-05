"""録画ガイドのデータモデル.

設計書の録画ガイド例（録画開始 / 画面表示 / 操作 / 10秒待機 / 録画停止）を
ステップ列として構造化する。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ステップ種別（UI のアイコン/色分けと実行制御に使う）
StepKind = Literal["start", "show", "action", "say", "wait", "stop"]


class RecordingStep(BaseModel):
    """録画手順の1ステップ。"""

    kind: StepKind = Field(description="ステップ種別")
    title: str = Field(description="短いラベル（例: 録画開始、画面表示）")
    instruction: str = Field(description="具体的に何をするかの説明")
    # wait ステップの待機秒数。その他のステップでは目安の所要秒数（0可）。
    duration_sec: int = Field(default=0, ge=0)


class RecordingGuide(BaseModel):
    """録画ガイド全体。"""

    topic: str = Field(description="対象の動画テーマ")
    steps: list[RecordingStep] = Field(default_factory=list)

    @property
    def total_sec(self) -> int:
        return sum(s.duration_sec for s in self.steps)


class GuideRequest(BaseModel):
    """録画ガイド生成リクエスト。"""

    # topic か project_id のどちらかを指定する（project_id 優先で企画を参照）。
    topic: str = ""
    notes: str = ""

    provider: str | None = None
    model: str | None = None

    # 指定するとプロジェクトの企画を参照し、生成したガイドを保存する
    project_id: int | None = None


class GuideResponse(BaseModel):
    guide: RecordingGuide
    provider: str
    model: str
    saved_to_project: int | None = None
