"""企画生成プロンプト.

AIへ渡すシステム/ユーザープロンプトを組み立てる。
出力は必ず JSON（VideoPlan 準拠）にさせ、後段で構造化する。
"""
from __future__ import annotations

from .models import PlanRequest

# フォーマット別の既定尺（秒）
DEFAULT_DURATION = {"short": 45, "long": 480}

# 出力してほしい JSON の形（モデルに提示するスキーマ例）
_JSON_SHAPE = """{
  "topic": "テーマ",
  "format": "short | long",
  "titles": ["タイトル候補1", "タイトル候補2", "タイトル候補3"],
  "target_duration_sec": 60,
  "hook": "冒頭の掴み（最初の3秒のセリフや映像）",
  "sections": [
    {"name": "セクション名", "duration_sec": 10, "description": "内容"}
  ],
  "cta": "視聴者に促す行動",
  "thumbnail_ideas": ["サムネイル案1", "サムネイル案2"]
}"""

SYSTEM_PROMPT = (
    "あなたはプロの動画プロデューサー兼ディレクターです。"
    "与えられたテーマから、視聴維持率と再生数を最大化する動画企画を作成します。"
    "冒頭の掴み・テンポ・CTAを重視し、実際に撮影/編集できる具体的な構成を提案してください。\n\n"
    "出力は必ず次の JSON 形式のみで返してください。"
    "説明文やコードフェンス(```）は付けず、JSON オブジェクトだけを出力します。\n"
    f"{_JSON_SHAPE}\n\n"
    "制約:\n"
    "- titles は 3〜5 個。クリックしたくなる具体的な表現にする。\n"
    "- sections の duration_sec の合計は target_duration_sec とほぼ一致させる。\n"
    "- short は縦型・テンポ重視、long は導入→本編→まとめの流れを意識する。\n"
    "- thumbnail_ideas は 2〜4 個。文字入れ案や構図を具体的に書く。\n"
    "- すべて日本語で書く。"
)


def build_user_prompt(req: PlanRequest, previous: list[str] | None = None) -> str:
    fmt = req.format
    if fmt == "auto":
        fmt_line = "フォーマット(short/long)はテーマに最適な方をあなたが選ぶ。"
    else:
        fmt_line = f"フォーマットは必ず「{fmt}」にする。"

    if req.target_duration_sec:
        dur_line = f"目標尺は約 {req.target_duration_sec} 秒。"
    elif fmt in ("short", "long"):
        dur_line = f"目標尺は約 {DEFAULT_DURATION[fmt]} 秒を目安にする。"
    else:
        dur_line = "目標尺はフォーマットに応じて妥当な長さにする。"

    lines = [
        f"テーマ: {req.topic}",
        fmt_line,
        dur_line,
    ]
    if req.notes.strip():
        lines.append(f"追加の要望: {req.notes.strip()}")

    # 同じプロジェクト・同じテーマで過去に決定した企画がある場合は、
    # それらと重複しない別バリエーションを作らせる。
    if previous:
        lines.append(
            "\n【重要】このテーマでは既に次の企画を作成・決定済みです（重複禁止）:"
        )
        for i, p in enumerate(previous, 1):
            lines.append(f"  過去案{i}: {p}")
        lines.append(
            "上記とは焦点・切り口・ターゲット視聴者・構成の順序を大きく変え、"
            "できるだけ新鮮で別方向のバリエーションにしてください。"
            "同じタイトルや同じ掴みは避けること。"
        )

    lines.append("上記を踏まえ、JSON で企画を出力してください。")
    return "\n".join(lines)
