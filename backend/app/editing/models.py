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


class StyleProfile(BaseModel):
    """参考にする編集者の「編集スタイル」プロファイル。

    AIが参考動画/クリエイター/特徴の記述から言語化する（実際の動画学習ではなく、
    スタイルの言語的モデル化）。編集提案時にこれへ寄せる。
    """

    creator: str = Field(default="", description="参考にした人/チャンネル名")
    summary: str = Field(default="", description="スタイルの一言要約")
    pacing: str = Field(default="", description="テンポ・カットの速さ")
    cut_style: str = Field(default="", description="カットの特徴（ジャンプカット等）")
    telop_style: str = Field(default="", description="テロップの使い方")
    sound_style: str = Field(default="", description="BGM・効果音の傾向")
    transitions: str = Field(default="", description="トランジション")
    hook_style: str = Field(default="", description="冒頭の掴み方")
    keywords: list[str] = Field(default_factory=list)

    def as_prompt_text(self) -> str:
        """編集提案プロンプトに差し込む説明文にまとめる。"""
        parts = []
        if self.creator:
            parts.append(f"参考クリエイター: {self.creator}")
        for label, val in [
            ("要約", self.summary),
            ("テンポ", self.pacing),
            ("カット", self.cut_style),
            ("テロップ", self.telop_style),
            ("音", self.sound_style),
            ("トランジション", self.transitions),
            ("掴み", self.hook_style),
        ]:
            if val:
                parts.append(f"{label}: {val}")
        return "\n".join(parts)


class LearnStyleRequest(BaseModel):
    """編集スタイル学習リクエスト。"""

    reference_url: str = Field(default="", description="参考動画のURL（YouTube等）")
    creator: str = Field(default="", description="参考にしたい人/チャンネル名")
    notes: str = Field(default="", description="好きな編集の特徴（自由記述）")

    provider: str | None = None
    model: str | None = None


class LearnStyleResponse(BaseModel):
    style: StyleProfile
    provider: str
    model: str
    source: str = ""  # 取得できた情報源（例: YouTube投稿者名/タイトル）


class SuggestRequest(BaseModel):
    """AI編集提案リクエスト。"""

    # 動画の長さ（秒）。probe 結果を渡すと現実的なタイムコードになる。
    duration_sec: float = Field(default=0, ge=0)
    # 台本/文字起こし（あると提案精度が上がる）
    script: str = ""
    goal: Literal["improve", "short", "auto"] = "auto"
    notes: str = ""
    # 寄せたい編集スタイル（学習済みプロファイルの説明文）
    style: str = ""

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


# ============================================================
# 動画編集（自動 / 手動）
# ============================================================
class MaterialSource(BaseModel):
    site: str
    url: str


class MaterialSuggestion(BaseModel):
    kind: str = "bgm"          # bgm | se | image | video
    kind_label: str = ""
    query: str = ""            # 探すキーワード
    reason: str = ""           # なぜ必要か
    sources: list[MaterialSource] = Field(default_factory=list)


class AutoEditRequest(BaseModel):
    input_path: str
    instructions: str = ""     # 「無音カット、要点にテロップ」等の指示
    has_subtitles: bool = False  # 動画に字幕あり→テロップを上寄せで被り回避
    vertical: bool = False       # 縦動画化（ショート・1080x1920）
    edit_heavy: bool = False     # 編集多め（テロップ/記号/素材を多くし「しゃべるだけ」回避）
    provider: str | None = None
    model: str | None = None


class AutoEditPlan(BaseModel):
    summary: str = ""
    remove_silence: bool = True
    cuts: list[CutSuggestion] = Field(default_factory=list)
    telops: list[TelopSuggestion] = Field(default_factory=list)
    materials: list[MaterialSuggestion] = Field(default_factory=list)


class AutoEditResponse(BaseModel):
    output_path: str
    duration_sec: float
    original_sec: float
    plan: AutoEditPlan
    warnings: list[str] = Field(default_factory=list)


class EditCut(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)


class EditTelop(BaseModel):
    time_sec: float = Field(ge=0)
    text: str = ""
    size: int = 54                       # フォントサイズ(px, 1280x720基準)
    color: str = "#ffffff"               # 文字色
    stroke: str = "#000000"              # 縁取り色
    x: float = 0.5                        # 水平位置(0..1)
    y: float | None = None               # 垂直位置(0..1)。未指定なら既定(下/字幕あれば上)
    bold: bool = True
    anim: str = "none"                   # none | fade | pop | slide


class EditOverlay(BaseModel):
    image: str                          # インポートした画像のパス
    start_sec: float = 0
    end_sec: float = 0                   # 0 なら最後まで
    position: str = "tr"                # tr/tl/br/bl/center


class ManualEditRequest(BaseModel):
    input_path: str
    cuts: list[EditCut] = Field(default_factory=list)        # 削除する区間
    telops: list[EditTelop] = Field(default_factory=list)    # テロップ
    vertical: bool = False                                    # 縦動画化
    volume: float = 1.0
    mute: bool = False
    bgm: str = ""                        # インポートしたBGMのパス
    bgm_volume: float = 0.3
    overlays: list[EditOverlay] = Field(default_factory=list)  # インポート画像
    has_subtitles: bool = False          # 字幕あり→テロップを上寄せ
    speed: float = 1.0                   # 再生速度倍率(0.5〜2.0)
    vfilter: str = "none"                # 色フィルタ名
    fade_in: float = 0.0                 # 開始フェード秒
    fade_out: float = 0.0                # 終了フェード秒


class ManualEditResponse(BaseModel):
    output_path: str
    duration_sec: float


class MaterialSearchRequest(BaseModel):
    query: str
    provider: str | None = None
    model: str | None = None


class MaterialSearchResponse(BaseModel):
    materials: list[MaterialSuggestion] = Field(default_factory=list)
