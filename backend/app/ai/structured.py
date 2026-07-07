"""構造化(JSON)生成の共通ヘルパー.

AI は時々 JSON でない応答や途中で切れた応答を返すため、
temperature>0 のサンプリングを活かして数回リトライしてから諦める。
これにより「AI生成時に時々エラーが起きる」不具合を大幅に減らす。
"""
from __future__ import annotations

import httpx

from .base import AIProvider, ChatMessage
from .jsonutil import JsonExtractError, extract_json
from ..logging_conf import get_logger

logger = get_logger(__name__)

# 一時的とみなして再試行する HTTP ステータス（レート制限・サーバ側障害）
_RETRY_STATUS = {429, 500, 502, 503, 504}


class AIServiceError(RuntimeError):
    """AIサービスへの接続/応答が一時的に失敗した（再試行しても回復せず）。"""


async def chat_json(
    provider: AIProvider,
    messages: list[ChatMessage],
    *,
    model: str,
    temperature: float = 0.7,
    attempts: int = 2,
) -> dict:
    """chat → JSON抽出 を、失敗時にリトライしながら実行する。

    再試行するのは「一時的な失敗」だけ:
    - JSON抽出に失敗（AIが時々JSON以外を返す）
    - ネットワーク接続/タイムアウト
    - レート制限(429)・サーバ側エラー(5xx)
    APIキー未設定・安全ブロック・400等の恒久的エラーは即座に伝播させる。
    """
    last_json: JsonExtractError | None = None
    last_net: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            result = await provider.chat(
                messages, model=model, temperature=temperature
            )
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_net = e
            logger.info("AI接続に失敗（%d/%d回目）: %s", i + 1, attempts, e)
            continue
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in _RETRY_STATUS:
                last_net = e
                logger.info("AI一時エラー%s（%d/%d回目）", code, i + 1, attempts)
                continue
            raise  # 400/401/403 等は恒久的
        try:
            return extract_json(result.text)
        except JsonExtractError as e:
            last_json = e
            logger.info(
                "JSON抽出に失敗（%d/%d回目）。応答先頭: %r",
                i + 1, attempts, (result.text or "")[:120],
            )
    if last_net is not None:
        raise AIServiceError(
            "AIサービスに接続できませんでした。ネットワークを確認して、"
            "少し時間をおいてから再試行してください。"
        ) from last_net
    raise last_json or JsonExtractError("AI応答からJSONを抽出できませんでした")
