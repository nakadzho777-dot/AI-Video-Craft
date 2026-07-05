"""編集支援のデータモデル.

AI編集提案（設計書の AI編集: カット位置 / テロップ / BGM候補 / テンポ改善 /
無音検出 / ショート動画化）を構造化する。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CutSuggestion(BaseModel):
    """カット提案（この区間を削除/短縮すると良い）。"""

    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    reason: str = Field(description="カット理由（例: 無音、冗長、言い直し）")


class TelopSuggestion(BaseModel):
    """テロップ提案。"""

    time_sec: float = Field(ge=0, description="表示タイミング（秒）")
    text: str = Field(description="テロップ文言")


class ShortPlan(BaseModel):
    """ショート動画化の案。"""

    target_duration_sec: int = Field(ge=0)
    vertical: bool = True
    segments: list[CutSuggestion] = Field(
        default_factory=list, description="ショートに使う見せ場の区間"
    )


class EditSuggestion(BaseModel):
    """AI編集提案の全体。"""

    cuts: list[CutSuggestion] = Field(default_factory=list)
    telops: list[TelopSuggestion] = Field(default_factory=list)
    bgm_suggestions: list[str] = Field(
        default_factory=list, description="BGM候補（ジャンル/雰囲気）"
    )
    tempo_tips: list[str] = Field(
        default_factory=list, description="テンポ改善のアドバイス"
    )
    short_plan: ShortPlan | None = None


class SuggestRequest(BaseModel):
    """AI編集提案リクエスト。"""

    # 動画の長さ（秒）。probe 結果を渡すと現実的なタイムコードになる。
    duration_sec: float = Field(default=0, ge=0)
    # 台本/文字起こし（あると提案精度が上がる）
    script: str = ""
    goal: Literal["improve", "short", "auto"] = "auto"
    notes: str = ""

    provider: str | None = None
    model: str | None = None

    # 指定するとプロジェクトの企画/台本を参照し、提案を保存する
    project_id: int | None = None


class SuggestResponse(BaseModel):
    suggestion: EditSuggestion
    provider: str
    model: str
    saved_to_project: int | None = None


# ---- FFmpeg 実処理系（提案とは別系統）----


class ProbeResponse(BaseModel):
    duration_sec: float
    width: int | None
    height: int | None


class SilenceRangeOut(BaseModel):
    start_sec: float
    end_sec: float
    duration_sec: float


class SilenceRequest(BaseModel):
    input_path: str
    noise_db: float = -30.0
    min_silence_sec: float = 0.5
