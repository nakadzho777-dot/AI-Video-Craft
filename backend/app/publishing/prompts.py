"""投稿テキスト生成プロンプト.

企画（あれば）とテーマから、各プラットフォーム最適化済みの投稿文を JSON で出力させる。
"""
from __future__ import annotations

_JSON_SHAPE = """{
  "youtube_titles": ["タイトル候補1", "タイトル候補2", "タイトル候補3"],
  "youtube_description": "説明欄本文（改行可）。概要・タイムスタンプ・リンク欄など。",
  "hashtags": ["#タグ1", "#タグ2", "#タグ3"],
  "pinned_comment": "固定コメント文",
  "booth_text": "BOOTH向けの紹介文",
  "x_post": "X投稿文（140字程度・ハッシュタグ込み）",
  "instagram_post": "Instagram投稿文（ハッシュタグ多め）",
  "tiktok_post": "TikTok投稿文（短くキャッチー）"
}"""

SYSTEM_PROMPT = (
    "あなたは動画マーケティングの専門家です。"
    "各プラットフォームのアルゴリズムと文化を理解し、"
    "クリック率・再生数・拡散を最大化する投稿テキストを作成します。\n\n"
    "出力は必ず次の JSON 形式のみで返してください。"
    "説明文やコードフェンス(```)は付けず、JSON オブジェクトだけを出力します。\n"
    f"{_JSON_SHAPE}\n\n"
    "ルール:\n"
    "- youtube_titles は 3〜5 個。クリックしたくなる具体的な表現。\n"
    "- youtube_description は検索も意識し、冒頭2行で内容が分かるようにする。\n"
    "- hashtags は各要素を必ず # から始める。\n"
    "- x_post は簡潔に、instagram_post はハッシュタグ多め、"
    "tiktok_post は短くキャッチーに、と媒体ごとに書き分ける。\n"
    "- すべて日本語で書く。"
)


def build_user_prompt(topic: str, plan_summary: str, notes: str) -> str:
    lines = [f"動画テーマ: {topic}"]
    if plan_summary:
        lines.append("参考にする企画:\n" + plan_summary)
    if notes.strip():
        lines.append(f"追加の要望: {notes.strip()}")
    lines.append("上記を踏まえ、投稿テキスト一式を JSON で出力してください。")
    return "\n".join(lines)
