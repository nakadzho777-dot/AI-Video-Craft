"""参考動画URLからの公開情報取得（ベストエフォート）.

YouTube の公開 oEmbed から投稿者名・タイトルを取得し、スタイル学習の
手がかりにする。取得できなくても機能は続行する（URLだけでもAIが推測）。
※ 動画そのものの解析・ダウンロードは行わない。
"""
from __future__ import annotations

import httpx

from ..logging_conf import get_logger

logger = get_logger(__name__)


async def fetch_reference_info(url: str) -> str:
    """URL から「投稿者 / タイトル」の説明文を返す。失敗時は空文字。"""
    url = url.strip()
    if not url:
        return ""
    is_youtube = "youtube.com" in url or "youtu.be" in url
    if not is_youtube:
        return ""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.info("oEmbed 取得失敗（続行）: %s", e)
        return ""
    author = data.get("author_name", "")
    title = data.get("title", "")
    parts = []
    if author:
        parts.append(f"投稿者: {author}")
    if title:
        parts.append(f"動画タイトル: {title}")
    return " / ".join(parts)
