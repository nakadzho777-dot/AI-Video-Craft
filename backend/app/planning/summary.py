"""企画（プラン）の要約ヘルパー.

保存済みの企画 JSON を、他機能（録画支援・投稿支援など）のプロンプトへ
渡すための簡潔なテキストに変換する。
"""
from __future__ import annotations


def summarize_plan(plan: dict) -> str:
    """企画 JSON(dict) から、プロンプトに渡す簡潔な要約テキストを作る。"""
    parts: list[str] = []
    if titles := plan.get("titles"):
        parts.append("タイトル案: " + " / ".join(titles[:3]))
    if hook := plan.get("hook"):
        parts.append(f"掴み: {hook}")
    sections = plan.get("sections") or []
    if sections:
        sec_lines = [
            f"  - {s.get('name', '')}({s.get('duration_sec', 0)}秒): "
            f"{s.get('description', '')}"
            for s in sections
        ]
        parts.append("構成:\n" + "\n".join(sec_lines))
    if cta := plan.get("cta"):
        parts.append(f"CTA: {cta}")
    return "\n".join(parts)
