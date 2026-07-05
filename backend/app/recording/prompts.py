"""録画ガイド生成プロンプト.

AIに、録画開始〜停止までの具体的な撮影手順を JSON で出力させる。
企画（プラン）がある場合はそれを文脈として渡す。
"""
from __future__ import annotations

# 企画要約は共通ヘルパーへ集約（後方互換のため再エクスポート）
from ..planning.summary import summarize_plan  # noqa: F401

_JSON_SHAPE = """{
  "topic": "テーマ",
  "steps": [
    {"kind": "start",  "title": "録画開始",   "instruction": "画面録画を開始する", "duration_sec": 0},
    {"kind": "show",   "title": "画面を表示", "instruction": "〇〇の画面を映す",   "duration_sec": 0},
    {"kind": "action", "title": "操作",       "instruction": "〇〇をクリックする", "duration_sec": 0},
    {"kind": "say",    "title": "話す",       "instruction": "『〇〇』と説明する",  "duration_sec": 0},
    {"kind": "wait",   "title": "10秒待機",   "instruction": "処理完了を待つ",     "duration_sec": 10},
    {"kind": "stop",   "title": "録画停止",   "instruction": "録画を停止する",     "duration_sec": 0}
  ]
}"""

SYSTEM_PROMPT = (
    "あなたはプロの撮影ディレクターです。"
    "動画の企画をもとに、初心者でもそのまま実行できる具体的な録画手順を作成します。\n\n"
    "出力は必ず次の JSON 形式のみで返してください。"
    "説明文やコードフェンス(```)は付けず、JSON オブジェクトだけを出力します。\n"
    f"{_JSON_SHAPE}\n\n"
    "ルール:\n"
    "- kind は start / show / action / say / wait / stop のいずれか。\n"
    "- 最初のステップは必ず kind=start（録画開始）、最後は kind=stop（録画停止）。\n"
    "- 各ステップは1つの動作に絞り、instruction は具体的に書く。\n"
    "- wait ステップには duration_sec（待機秒数）を必ず入れる。\n"
    "- 企画の構成（セクション）に沿って、撮影しやすい順序で並べる。\n"
    "- ステップ数は 6〜14 個程度。すべて日本語で書く。"
)


def build_user_prompt(topic: str, plan_summary: str, notes: str) -> str:
    lines = [f"テーマ: {topic}"]
    if plan_summary:
        lines.append("参考にする企画:\n" + plan_summary)
    if notes.strip():
        lines.append(f"追加の要望: {notes.strip()}")
    lines.append("上記に沿って、録画手順を JSON で出力してください。")
    return "\n".join(lines)
