"""宣伝記事生成プロンプト.

1) キーワード案出し（キーワード未指定時）
2) 各キーワードから SEO 記事本体を生成
"""
from __future__ import annotations

# --- キーワード案出し ---
KEYWORD_SYSTEM = (
    "あなたはSEOストラテジストです。"
    "指定された宣伝対象について、検索流入が見込めるロングテール寄りのキーワードを提案します。\n"
    "出力は次の JSON のみ。説明やコードフェンスは不要:\n"
    '{"keywords": ["キーワード1", "キーワード2"]}\n'
    "各キーワードは日本語で、検索意図が異なるものを選ぶ。"
)


def build_keyword_prompt(topic: str, count: int, tone: str) -> str:
    lines = [
        f"宣伝対象: {topic}",
        f"キーワードを {count} 個提案してください。",
    ]
    if tone.strip():
        lines.append(f"ターゲット/トーン: {tone.strip()}")
    return "\n".join(lines)


# --- 記事本体 ---
_ARTICLE_SHAPE = """{
  "title": "SEOを意識した記事タイトル",
  "slug": "url-slug-in-english",
  "target_keyword": "主要キーワード",
  "meta_description": "検索結果に出る120字程度の説明",
  "keywords": ["関連キーワード1", "関連キーワード2"],
  "outline": ["## 見出し1", "## 見出し2", "### 小見出し"],
  "body_markdown": "# タイトル\\n\\n本文をMarkdownで..."
}"""

ARTICLE_SYSTEM = (
    "あなたはプロのSEOライターです。"
    "指定キーワードで検索上位を狙える、読者に価値のある宣伝記事を作成します。\n\n"
    "出力は必ず次の JSON 形式のみ。説明文やコードフェンス(```)は付けない:\n"
    f"{_ARTICLE_SHAPE}\n\n"
    "ルール:\n"
    "- title と本文冒頭に target_keyword を自然に含める。\n"
    "- body_markdown は見出し(##)・箇条書き・CTAを含む800〜1500字程度の本文。\n"
    "- 誇大表現や虚偽は避け、具体的な利点を書く。\n"
    "- slug は半角英数とハイフンのみ。\n"
    "- すべて日本語（slug を除く）。"
)


def build_article_prompt(topic: str, keyword: str, tone: str) -> str:
    lines = [
        f"宣伝対象: {topic}",
        f"狙うキーワード: {keyword}",
    ]
    if tone.strip():
        lines.append(f"ターゲット/トーン: {tone.strip()}")
    lines.append("このキーワードで1本、SEO宣伝記事を JSON で出力してください。")
    return "\n".join(lines)
