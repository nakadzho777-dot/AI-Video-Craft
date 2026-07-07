"""音声合成エンジンの抽象化.

既定は edge-tts（無料・追加導入なし）。設定で AquesTalk（本物のゆっくり声）を
指定し DLL があればそちらを使う。AquesTalk 部分は DLL 入手後に有効化する受け口。
"""
from __future__ import annotations

import asyncio
import os

import edge_tts

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)

# ゆっくりボイス（AquesTalk）の入手先。VOICEVOX の URL は voicevox.DOWNLOAD_URL。
AQUESTALK_DOWNLOAD_URL = "https://www.a-quest.com/products/aquestalk.html"

_AQ_DLLS = ("AquesTalk.dll", "AquesTalk10.dll", "AquesTalk2.dll", "AquesTalk1.dll")


def _aq_candidate_dirs() -> list[str]:
    """AquesTalk のDLLがありそうな場所（自動検出用）。"""
    dirs: list[str] = []
    # 設定/環境変数での明示指定があれば最優先
    d = (getattr(get_settings(), "aquestalk_dir", "") or "").strip()
    if d:
        dirs.append(d)
    # アプリのデータフォルダに置かれた voices/ も見る
    try:
        dirs.append(str(get_settings().data_dir / "voices"))
    except Exception:
        pass
    # よくあるインストール先を走査
    home = os.path.expanduser("~")
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "C:\\",
        home,
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
    ]
    names = ["AquesTalk", "AquesTalkPlayer", "AqKanji2Koe", "aquestalk", "ゆっくり"]
    for r in roots:
        if not r:
            continue
        for n in names:
            dirs.append(os.path.join(r, n))
    return dirs


def detect_aquestalk() -> str:
    """AquesTalk のDLLがあるフォルダを自動検出。見つからなければ空文字。"""
    for d in _aq_candidate_dirs():
        try:
            if d and any(os.path.exists(os.path.join(d, dll)) for dll in _AQ_DLLS):
                return d
        except Exception:
            continue
    return ""


def get_aquestalk_dir() -> str:
    """互換用: 検出されたフォルダを返す。"""
    return detect_aquestalk()


def aquestalk_available() -> bool:
    """AquesTalk が使える状態か（DLL を自動検出できたか）。"""
    return bool(detect_aquestalk())


def _aquestalk_synth(text: str, path: str) -> None:
    """AquesTalk で音声合成（DLL入手後に実装・検証を完了させる受け口）。

    販売アプリで使うには AquesTalk の商用ライセンスと、漢字読み用の
    AqKanji2Koe が必要。DLL 配置後にここを ctypes で実装する。
    """
    raise NotImplementedError(
        "AquesTalk 連携は DLL 配置後に有効化されます（現状は edge-tts を使用）"
    )


async def synth_line(text: str, voice: str, path: str) -> str:
    """1行を音声合成してファイルへ保存。使用エンジン名を返す。"""
    # VOICEVOX 音声（id が 'vv:<style_id>'）
    if voice.startswith("vv:"):
        try:
            from . import voicevox

            await voicevox.synth(text, int(voice[3:]), path)
            return "voicevox"
        except Exception as e:  # 失敗時は edge-tts にフォールバック
            logger.info("VOICEVOX 失敗（%s）→ edge-tts", e)
            voice = "ja-JP-NanamiNeural"
    if aquestalk_available():
        try:
            await asyncio.to_thread(_aquestalk_synth, text, path)
            return "aquestalk"
        except Exception as e:  # 失敗時は edge-tts にフォールバック
            logger.info("AquesTalk 未使用（%s）→ edge-tts", e)
    await edge_tts.Communicate(text, voice).save(path)
    return "edge-tts"
