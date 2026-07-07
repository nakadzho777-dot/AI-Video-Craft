"""VOICEVOX 連携（無料・商用可・多数のキャラ声）.

VOICEVOX エンジン（既定 http://localhost:50021）が起動していれば、
ずんだもん等の多数の音声が使える。未起動なら利用不可として edge-tts に戻す。

公式: https://voicevox.hiroshiba.jp/
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)

DOWNLOAD_URL = "https://voicevox.hiroshiba.jp/"


def base_url() -> str:
    return (get_settings().voicevox_url or "http://127.0.0.1:50021").rstrip("/")


async def available() -> bool:
    """VOICEVOX エンジンが起動しているか（ポート開通を素の TCP で高速確認）。

    httpx は初回コールドスタートが遅いため、まずポートの開通だけを見る。
    """
    u = urlparse(base_url())
    host, port = u.hostname or "127.0.0.1", u.port or 50021
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=0.5
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def speakers() -> list[dict]:
    """話者一覧を返す（[{name, styles:[{name, id}]}]）。"""
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(base_url() + "/speakers")
        r.raise_for_status()
        return r.json()


async def synth(text: str, style_id: int, path: str) -> None:
    """text を style_id の声で合成して WAV を path に保存する。"""
    async with httpx.AsyncClient(timeout=60.0) as c:
        q = await c.post(
            base_url() + "/audio_query",
            params={"text": text, "speaker": style_id},
        )
        q.raise_for_status()
        s = await c.post(
            base_url() + "/synthesis",
            params={"speaker": style_id},
            content=q.content,
            headers={"Content-Type": "application/json"},
        )
        s.raise_for_status()
        with open(path, "wb") as f:
            f.write(s.content)


async def voice_options() -> list[dict]:
    """UI 用の音声候補（id は 'vv:<style_id>'）。エンジン未起動なら空。"""
    if not await available():
        return []
    out: list[dict] = []
    try:
        for sp in await speakers():
            name = sp.get("name", "")
            for st in sp.get("styles", []):
                out.append(
                    {"id": f"vv:{st['id']}", "label": f"{name}（{st.get('name', '')}）"}
                )
    except Exception as e:
        logger.info("VOICEVOX 話者取得に失敗: %s", e)
    return out
