"""AI自動撮影の入出力モデル."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# ブラウザ操作の種類
ActionKind = Literal["goto", "click", "fill", "press", "scroll", "wait"]


class AutopilotStep(BaseModel):
    """1ステップ = 1つのブラウザ操作 ＋ その間のナレーション."""

    title: str = ""                 # 短いラベル（UI表示用）
    action: ActionKind = "wait"     # 操作の種類
    target: str = ""                # click/fill の対象（見えているテキスト等）
    value: str = ""                 # fill:入力文字 / press:キー / goto:URL / scroll:量
    narration: str = ""             # このステップで読み上げる文（日本語）


class AutopilotPlan(BaseModel):
    """自動撮影の台本全体."""

    title: str = ""
    url: str = ""                   # 最初に開くURL
    steps: List[AutopilotStep] = Field(default_factory=list)


# ---- API リクエスト / レスポンス ----


class PlanRequest(BaseModel):
    url: str
    urls: List[str] = Field(default_factory=list)  # 複数ページ（AIが行き来できる）
    topic: str = ""
    notes: str = ""
    instructions: str = ""          # ユーザーが指示する手順（あれば厳守）
    style: str = "normal"           # normal | kaisetsu(ゆっくり解説) | jikkyou(ゆっくり実況)
    provider: Optional[str] = None
    model: Optional[str] = None
    project_id: Optional[int] = None


class PlanResponse(BaseModel):
    plan: AutopilotPlan
    provider: str
    model: str


class RunRequest(BaseModel):
    plan: AutopilotPlan
    voice: str = "ja-JP-NanamiNeural"
    subtitles: bool = True          # ナレーションを字幕で焼き込む
    yukkuri: bool = False           # ゆっくりキャラを重ねて解説風にする
    yukkuri_name: str = "霊夢"
    yukkuri_avatar: str = ""        # 立ち絵画像のパス（空なら丸顔）
    yukkuri_show: bool = True       # キャラを表示するか
    allowed_urls: List[str] = Field(default_factory=list)  # 開いてよいURL
    token: str = ""                 # キャンセル用トークン
    narrate: bool = True            # ナレーションを付けるか（素材録画時はFalse）


class RunResponse(BaseModel):
    video_path: str                 # 生成したMP4の絶対パス
    duration_sec: float
    steps_run: int
    warnings: List[str] = Field(default_factory=list)


# ============================================================
# デスクトップアプリ版（ウィンドウ録画＋pywinauto自動操作）
# ============================================================
DesktopActionKind = Literal["click", "type", "key", "scroll", "wait"]


class DesktopStep(BaseModel):
    title: str = ""
    action: DesktopActionKind = "wait"
    target: str = ""                # click: ボタン/メニュー等のテキスト
    value: str = ""                 # type:入力文字 / key:キー(例 {ENTER}) / scroll:量
    narration: str = ""


class DesktopPlan(BaseModel):
    title: str = ""
    window_title: str = ""          # 対象ウィンドウのタイトル
    steps: List[DesktopStep] = Field(default_factory=list)


class DesktopPlanRequest(BaseModel):
    window_title: str
    topic: str = ""
    notes: str = ""
    instructions: str = ""          # ユーザーが指示する手順（あれば厳守）
    provider: Optional[str] = None
    model: Optional[str] = None


class DesktopPlanResponse(BaseModel):
    plan: DesktopPlan
    provider: str
    model: str


class DesktopRunRequest(BaseModel):
    plan: DesktopPlan
    voice: str = "ja-JP-NanamiNeural"
    subtitles: bool = True
    token: str = ""                 # キャンセル用トークン
    narrate: bool = True            # ナレーションを付けるか（素材録画時はFalse）
