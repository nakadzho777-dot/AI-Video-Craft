"""ゆっくり解説の入出力モデル."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Speaker = Literal["a", "b"]


class YukkuriLine(BaseModel):
    speaker: Speaker = "a"          # a=左キャラ（聞き手） / b=右キャラ（解説役）
    text: str = ""


class YukkuriScript(BaseModel):
    title: str = ""
    lines: List[YukkuriLine] = Field(default_factory=list)


class CharacterConfig(BaseModel):
    name_a: str = "アカリ"          # 左・聞き手（1人モード時はこのキャラのみ）
    name_b: str = "ソウ"            # 右・解説役
    voice_a: str = "ja-JP-NanamiNeural"
    voice_b: str = "ja-JP-KeitaNeural"
    single: bool = False            # 1人モード（1キャラだけ表示）
    show_chars: bool = True         # キャラ（丸顔/立ち絵）を出すか
    avatar_a: str = ""              # 立ち絵画像のパス（空なら丸顔＝名前アイコン）
    avatar_b: str = ""              # 立ち絵画像のパス（右キャラ）


# ---- API ----
class ScriptRequest(BaseModel):
    topic: str
    notes: str = ""
    instructions: str = ""          # 手順/流れの指示（任意）
    mode: str = "kaisetsu"          # kaisetsu(解説) | jikkyou(実況)
    target_sec: float = 0           # 実況: 元動画の長さ（本数の目安に使う）
    speakers: int = 2               # 1(一人) | 2(掛け合い)
    name_a: str = "アカリ"
    name_b: str = "ソウ"
    provider: Optional[str] = None
    model: Optional[str] = None


class ScriptResponse(BaseModel):
    script: YukkuriScript
    provider: str
    model: str


class RenderRequest(BaseModel):
    script: YukkuriScript
    chars: CharacterConfig = Field(default_factory=CharacterConfig)


class RenderResponse(BaseModel):
    video_path: str
    duration_sec: float
    lines: int
    voice_engine: str               # 実際に使った音声エンジン
    warnings: List[str] = Field(default_factory=list)


class JikkyouRenderRequest(BaseModel):
    base_video: str                 # 実況を乗せる元動画のパス
    script: YukkuriScript
    chars: CharacterConfig = Field(default_factory=CharacterConfig)
    voice_a: str = "ja-JP-NanamiNeural"
    voice_b: str = "ja-JP-KeitaNeural"
    subtitles: bool = True
    keep_original_audio: bool = True  # 元動画の音を残してミックスするか
