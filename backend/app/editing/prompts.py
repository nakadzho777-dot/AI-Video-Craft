"""編集提案プロンプト.

動画情報（長さ）と台本を元に、AIへ編集案を JSON で出力させる。
"""
from __future__ import annotations

from .models import SuggestRequest

_JSON_SHAPE = """{
  "cuts": [
    {"start_sec": 12.0, "end_sec": 15.5, "reason": "無音・間延び"}
  ],
  "telops": [
    {"time_sec": 3.0, "text": "画面に出すテロップ"}
  ],
  "bgm_suggestions": ["明るいローファイ", "疾走感のあるEDM"],
  "tempo_tips": ["冒頭5秒を短くして結論を先に見せる"],
  "short_plan": {
    "target_duration_sec": 30,
    "vertical": true,
    "segments": [{"start_sec": 40.0, "end_sec": 70.0, "reason": "一番の見せ場"}]
  }
}"""

SYSTEM_PROMPT = (
    "あなたはプロの動画編集者です。"
    "動画の長さと台本をもとに、視聴維持率を高める編集案を提案します。\n\n"
    "出力は必ず次の JSON 形式のみで返してください。"
    "説明文やコードフェンス(```)は付けず、JSON オブジェクトだけを出力します。\n"
    f"{_JSON_SHAPE}\n\n"
    "ルール:\n"
    "- タイムコード(start_sec/end_sec/time_sec)は動画の長さの範囲内にする。\n"
    "- cuts は冗長・無音・言い直しなど削るべき箇所を挙げる。\n"
    "- telops は要点や数字を強調する短い文言にする。\n"
    "- short_plan は goal に応じて設定（不要なら null 可）。\n"
    "- すべて日本語。値は現実的で具体的にする。"
)


def build_user_prompt(req: SuggestRequest) -> str:
    goal_map = {
        "improve": "通常動画としての完成度を上げる編集案。",
        "short": "ショート動画化を主目的にした編集案（short_plan 必須）。",
        "auto": "動画に最適な編集案（必要ならショート化も提案）。",
    }
    lines = [
        f"動画の長さ: 約 {req.duration_sec:.0f} 秒",
        f"目的: {goal_map[req.goal]}",
    ]
    if req.script.strip():
        lines.append("台本/文字起こし:\n" + req.script.strip())
    if req.notes.strip():
        lines.append(f"追加の要望: {req.notes.strip()}")
    lines.append("上記を踏まえ、編集案を JSON で出力してください。")
    return "\n".join(lines)
