"""AI自動撮影サービス.

- 台本生成: AIプロバイダーに投げて AutopilotPlan を構造化。
- 実行: Playwright(同期API・別スレッド) でブラウザを自動操作しつつ録画し、
  edge-tts でナレーションを合成、imageio-ffmpeg で音声と映像を1本のMP4に。

Windows の uvicorn(asyncio) 上では Playwright 非同期APIが不安定なため、
録画は同期APIを asyncio.to_thread で別スレッド実行して回避する。
"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import subprocess
import tempfile
import time
from typing import List, Tuple

import edge_tts
import imageio_ffmpeg
from playwright.sync_api import sync_playwright

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .models import AutopilotPlan, AutopilotStep, PlanRequest, RunResponse
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


def _resolve_bundled_ffmpeg() -> str:
    """同梱 ffmpeg のパス。get_ffmpeg_exe が一時的に失敗（OneDrive の
    ファイル一時ロック等）してもインポートを落とさず、既知パスへフォールバック。"""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.warning("get_ffmpeg_exe 失敗、既知パスにフォールバック: %s", e)
        guess = os.path.join(
            os.path.dirname(imageio_ffmpeg.__file__),
            "binaries", "ffmpeg-win-x86_64-v7.1.exe",
        )
        return guess if os.path.exists(guess) else "ffmpeg"


FFMPEG = _resolve_bundled_ffmpeg()
VIEWPORT = {"width": 1280, "height": 720}

# 実行中の自動操作をキャンセルするためのトークン集合
_CANCELLED: set[str] = set()


def request_cancel(token: str) -> None:
    if token:
        _CANCELLED.add(token)


def is_cancelled(token: str) -> bool:
    return bool(token) and token in _CANCELLED


def clear_cancel(token: str) -> None:
    _CANCELLED.discard(token)
# Windows で subprocess のウィンドウを出さない
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class PlanParseError(RuntimeError):
    """AI応答を台本として解釈できなかった。"""


# ============================================================
# 台本生成（AI）
# ============================================================
class AutopilotPlanService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(self, req: PlanRequest, *, model: str) -> AutopilotPlan:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_user_prompt(
                    req.url, req.topic, req.notes, req.instructions,
                    style=req.style, urls=req.urls,
                ),
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.5
            )
        except JsonExtractError as e:
            raise PlanParseError(str(e)) from e

        data.setdefault("url", req.url)
        if not data.get("url"):
            data["url"] = req.url
        try:
            plan = AutopilotPlan.model_validate(data)
        except Exception as e:
            raise PlanParseError(f"台本の形式が不正です: {e}") from e
        if not plan.steps:
            raise PlanParseError("ステップが生成されませんでした")
        # URLは入力を優先（AIが書き換えても実URLを使う）
        plan.url = req.url
        return plan


# ============================================================
# 音声（edge-tts / 無音）
# ============================================================
async def _tts(text: str, voice: str, path: str) -> None:
    await edge_tts.Communicate(text, voice).save(path)


def _silence(path: str, seconds: float) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", f"{seconds:.2f}", "-q:a", "9", path],
        capture_output=True, creationflags=_NO_WINDOW,
    )


def _duration(path: str) -> float:
    r = subprocess.run(
        [FFMPEG, "-i", path], capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


# ============================================================
# ブラウザ操作（同期・別スレッドで実行）
# ============================================================
def _looks_like_selector(s: str) -> bool:
    return bool(re.match(r"^[.#\[]", s)) or (
        " " not in s and any(c in s for c in ".#[]>")
    )


def _click(pg, target: str) -> None:
    target = (target or "").strip()
    if not target:
        return
    candidates = [
        lambda: pg.get_by_role("button", name=target),
        lambda: pg.get_by_role("link", name=target),
        lambda: pg.get_by_text(target, exact=False),
    ]
    for make in candidates:
        try:
            make().first.click(timeout=3000)
            return
        except Exception:
            continue
    # 見出しテキストで見つからず、CSSセレクタらしい場合のみ最後に試す
    if _looks_like_selector(target):
        pg.click(target, timeout=3000)
        return
    raise RuntimeError(f"クリック対象が見つかりません: {target}")


def _fill(pg, target: str, value: str) -> None:
    target = (target or "").strip()
    for make in (lambda: pg.get_by_label(target), lambda: pg.get_by_placeholder(target)):
        try:
            make().first.fill(value, timeout=3500)
            return
        except Exception:
            continue
    pg.fill(target, value, timeout=3500)


def _do_action(pg, st: AutopilotStep) -> None:
    a = st.action
    if a == "goto" and st.value:
        pg.goto(st.value, wait_until="domcontentloaded", timeout=30000)
    elif a == "click":
        _click(pg, st.target)
    elif a == "fill":
        _fill(pg, st.target, st.value)
    elif a == "press":
        pg.keyboard.press(st.value or "Enter")
    elif a == "scroll":
        amount = 600
        try:
            amount = int(st.value)
        except (TypeError, ValueError):
            pass
        pg.mouse.wheel(0, amount)
    # "wait" は操作なし（後続の待機で尺を確保）


def _url_allowed(url: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    return any(url.strip().startswith(a.strip()) for a in allowed if a.strip())


def _record_sync(
    plan: AutopilotPlan, waits_ms: List[int], work_dir: str,
    allowed_urls: List[str] | None = None, token: str = "",
) -> Tuple[str, List[str]]:
    """ブラウザを自動操作しつつ録画し、webmのパスを返す（同期）。"""
    warnings: List[str] = []
    allowed = allowed_urls or []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=work_dir,
            record_video_size=VIEWPORT,
        )
        pg = ctx.new_page()
        try:
            pg.goto(plan.url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            warnings.append(f"URLの読み込みに失敗しました: {e}")
        pg.wait_for_timeout(1200)  # 冒頭の間

        for i, st in enumerate(plan.steps):
            if is_cancelled(token):
                warnings.append("ユーザー操作によりキャンセルされました。")
                break
            try:
                # 指定URL以外への移動はブロック
                if st.action == "goto" and not _url_allowed(st.value, allowed):
                    warnings.append(
                        f"ステップ{i + 1}: 指定外URLへの移動をブロックしました（{st.value}）"
                    )
                else:
                    _do_action(pg, st)
            except Exception as e:
                warnings.append(
                    f"ステップ{i + 1}({st.action} {st.target}) をスキップ: {e}"
                )
            pg.wait_for_timeout(max(1200, waits_ms[i]))

        ctx.close()  # ← これで動画が確定・書き出し
        browser.close()

    vids = glob.glob(os.path.join(work_dir, "*.webm"))
    if not vids:
        raise RuntimeError("録画ファイルが生成されませんでした")
    return vids[0], warnings


def _srt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(steps, durations: List[float], path: str) -> bool:
    """各ステップのナレーションを、音声トラックに合わせた字幕(SRT)にする。"""
    lines: List[str] = []
    t = 0.0
    idx = 1
    for st, d in zip(steps, durations):
        text = (st.narration or "").strip()
        if text:
            lines.append(str(idx))
            lines.append(f"{_srt_ts(t)} --> {_srt_ts(t + d)}")
            lines.append(text)
            lines.append("")
            idx += 1
        t += d
    if idx == 1:
        return False  # 字幕なし
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


# 字幕スタイル（白文字＋黒縁・下寄せ・日本語フォント）
_SUB_STYLE = (
    "Fontname=Meiryo,FontSize=18,PrimaryColour=&H00FFFFFF&,"
    "OutlineColour=&H00000000&,BorderStyle=1,Outline=2,Shadow=1,MarginV=32"
)


def _finalize(
    work_dir: str,
    video_webm: str,
    audio_paths: List[str],
    out_path: str,
    srt_name: str | None = None,
    char_overlay: str | None = None,
) -> None:
    """音声を連結し、映像とmux（任意で字幕・ゆっくりキャラを重ねる）してMP4を書き出す。"""
    # 音声連結。エンジン(edge-tts=mp3 / VOICEVOX=wav)で形式が混在しても壊れないよう、
    # concat デムーサ(-c copy)ではなく concat フィルタで再エンコードして繋ぐ。
    full_audio = os.path.join(work_dir, "full.m4a")
    concat_cmd: List[str] = [FFMPEG, "-y"]
    for ap in audio_paths:
        concat_cmd += ["-i", ap]
    concat_cmd += [
        "-filter_complex", f"concat=n={len(audio_paths)}:v=0:a=1[a]",
        "-map", "[a]", "-c:a", "aac", full_audio,
    ]
    subprocess.run(concat_cmd, capture_output=True, creationflags=_NO_WINDOW)
    common = [
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart", "-shortest", out_path,
    ]
    if char_overlay:
        # ゆっくりキャラ(透過PNG)を重ねてから字幕を焼く
        vchain = "[0:v][2:v]overlay=0:0[v1]"
        if srt_name:
            vchain += f";[v1]subtitles={srt_name}:force_style='{_SUB_STYLE}'[vout]"
        else:
            vchain += ";[v1]null[vout]"
        cmd = [
            FFMPEG, "-y", "-i", video_webm, "-i", full_audio, "-i", char_overlay,
            "-filter_complex", vchain, "-map", "[vout]", "-map", "1:a",
        ] + common
    else:
        cmd = [FFMPEG, "-y", "-i", video_webm, "-i", full_audio]
        if srt_name:
            cmd += ["-vf", f"subtitles={srt_name}:force_style='{_SUB_STYLE}'"]
        cmd += common
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=work_dir, creationflags=_NO_WINDOW
    )
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"動画の合成に失敗しました: {r.stderr[-400:]}")


# ============================================================
# 実行（TTS→録画→合成）
# ============================================================
async def run_autopilot(
    plan: AutopilotPlan, voice: str, out_dir: str, subtitles: bool = True,
    yukkuri: bool = False, yukkuri_name: str = "霊夢",
    yukkuri_avatar: str = "", yukkuri_show: bool = True,
    allowed_urls: List[str] | None = None, token: str = "",
    narrate: bool = True,
) -> RunResponse:
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="aivc_ap_")
    warnings: List[str] = []

    # 1) ステップごとに音声（ナレーション or 無音）を用意し、尺を測る
    #    narrate=False（ゆっくり用の素材録画など）なら全て無音にする
    audio_paths: List[str] = []
    waits_ms: List[int] = []
    durations: List[float] = []
    for i, st in enumerate(plan.steps):
        ap = os.path.join(work, f"a{i}.mp3")
        text = (st.narration or "").strip() if narrate else ""
        if text:
            try:
                await _tts(text, voice, ap)
            except Exception as e:
                warnings.append(f"ステップ{i + 1} のナレーション生成に失敗: {e}")
                _silence(ap, 2.5)
        else:
            _silence(ap, 2.5)
        dur = max(1.2, _duration(ap))
        audio_paths.append(ap)
        waits_ms.append(int(dur * 1000))
        durations.append(dur)

    # 2) ブラウザ自動操作＋録画（同期APIを別スレッドで）
    video_webm, rec_warn = await asyncio.to_thread(
        _record_sync, plan, waits_ms, work, allowed_urls, token
    )
    clear_cancel(token)
    warnings.extend(rec_warn)

    # 3) 字幕(SRT)を生成（ナレーションを音声トラックに合わせて）
    srt_name: str | None = None
    if subtitles:
        srt_path = os.path.join(work, "sub.srt")
        if _build_srt(plan.steps, durations, srt_path):
            srt_name = "sub.srt"

    # 4) 音声連結＋mux（＋字幕焼き込み）（別スレッド）
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"AIVideoCraft_auto_{ts}.mp4")
    # ゆっくりキャラのオーバーレイ（透過PNG）
    char_overlay = None
    if yukkuri:
        try:
            from ..yukkuri.models import CharacterConfig
            from ..yukkuri.render import render_overlay

            char_overlay = os.path.join(work, "yk_char.png")
            render_overlay(
                CharacterConfig(
                    name_a=yukkuri_name, single=True,
                    show_chars=yukkuri_show, avatar_a=yukkuri_avatar or "",
                ),
                char_overlay,
            )
        except Exception as e:
            warnings.append(f"ゆっくりキャラの描画に失敗: {e}")
            char_overlay = None

    await asyncio.to_thread(
        _finalize, work, video_webm, audio_paths, out_path, srt_name, char_overlay
    )

    return RunResponse(
        video_path=out_path,
        duration_sec=round(_duration(out_path), 2),
        steps_run=len(plan.steps),
        warnings=warnings,
    )


# 利用可能な日本語音声（UI用）
JA_VOICES = [
    {"id": "ja-JP-NanamiNeural", "label": "Nanami（女性・標準）"},
    {"id": "ja-JP-KeitaNeural", "label": "Keita（男性・標準）"},
]
