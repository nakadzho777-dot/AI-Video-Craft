"""デスクトップアプリ版 自動撮影.

対象ウィンドウを ffmpeg(gdigrab) で録画しつつ、pywinauto で「できる範囲の」
自動操作を行う。ナレーション(edge-tts)＋字幕＋合成は service.py を再利用。

Web版(Playwright)と違い、デスクトップは操作対象を確実に指定できないことが多いため
「録画＋ナレーション＋字幕」を土台に、操作は best-effort（失敗しても続行）とする。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from typing import List, Tuple

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .models import DesktopPlan, DesktopPlanRequest, DesktopStep, RunResponse
from .prompts import DESKTOP_SYSTEM_PROMPT, build_desktop_prompt
from .service import (
    FFMPEG,
    _NO_WINDOW,
    _build_srt,
    _duration,
    _finalize,
    _silence,
    _tts,
    PlanParseError,
)

logger = get_logger(__name__)


# ============================================================
# 開いているウィンドウ一覧（ユーザーが対象を選ぶ用）
# ============================================================
def list_windows() -> List[str]:
    """可視のトップレベルウィンドウのタイトル一覧を返す。"""
    try:
        import win32gui  # pywin32（pywinauto の依存）
    except Exception:
        return []

    titles: List[str] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        t = win32gui.GetWindowText(hwnd)
        if t and t.strip() and len(t) < 200:
            titles.append(t)

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        logger.warning("ウィンドウ列挙に失敗: %s", e)
    # 重複除去（順序維持）。自分自身っぽいものは末尾でもよいが、そのまま返す。
    seen = set()
    uniq = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


# ============================================================
# 台本生成（AI）
# ============================================================
class DesktopPlanService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(self, req: DesktopPlanRequest, *, model: str) -> DesktopPlan:
        messages = [
            ChatMessage(role="system", content=DESKTOP_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_desktop_prompt(
                    req.window_title, req.topic, req.notes, req.instructions
                ),
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.5
            )
        except JsonExtractError as e:
            raise PlanParseError(str(e)) from e
        data["window_title"] = req.window_title
        try:
            plan = DesktopPlan.model_validate(data)
        except Exception as e:
            raise PlanParseError(f"台本の形式が不正です: {e}") from e
        if not plan.steps:
            raise PlanParseError("ステップが生成されませんでした")
        plan.window_title = req.window_title
        return plan


# ============================================================
# 自動操作（pywinauto）
# ============================================================
# type_keys で特別扱いされる文字をエスケープ
_KEY_SPECIALS = set("{}()[]+^%~")


def _escape_type(text: str) -> str:
    out = []
    for ch in text:
        out.append("{" + ch + "}" if ch in _KEY_SPECIALS else ch)
    return "".join(out)


def _desktop_click(win, target: str) -> None:
    target = (target or "").strip()
    if not target:
        return
    last_err: Exception | None = None
    for ctype in ("Button", "MenuItem", "TabItem", "ListItem", "Text", None):
        try:
            kw = {"title": target}
            if ctype:
                kw["control_type"] = ctype
            win.child_window(**kw).click_input()
            return
        except Exception as e:  # 見つからない/クリック不可
            last_err = e
            continue
    raise RuntimeError(f"コントロールが見つかりません: {target} ({last_err})")


def _do_desktop_action(win, st: DesktopStep) -> None:
    a = st.action
    if a == "type":
        win.type_keys(_escape_type(st.value), with_spaces=True, pause=0.03)
    elif a == "key":
        win.type_keys(st.value or "{ENTER}", pause=0.05)
    elif a == "click":
        _desktop_click(win, st.target)
    elif a == "scroll":
        amount = 3
        try:
            amount = int(st.value)
        except (TypeError, ValueError):
            pass
        try:
            win.wheel_mouse_input(wheel_dist=-abs(amount))
        except Exception:
            pass
    # "wait" は操作なし


def _screen_size() -> Tuple[int, int]:
    """プライマリモニタの画面サイズ(幅,高さ)。"""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080


def _window_region(win) -> Tuple[int, int, int, int] | None:
    """ウィンドウの画面上の矩形(左,上,幅,高さ)。画面内にクランプ。取得不可なら None。

    最大化ウィンドウは枠の分だけ画面外(例 -8px, right=1928)にはみ出すため、
    画面サイズにクランプしないと gdigrab が「範囲が画面外」でエラーになる。
    """
    try:
        r = win.rectangle()
        sw, sh = _screen_size()
        left = min(max(0, r.left), sw - 2)
        top = min(max(0, r.top), sh - 2)
        right = min(r.right, sw)
        bottom = min(r.bottom, sh)
        width = (right - left) // 2 * 2     # h264 は偶数サイズ必須
        height = (bottom - top) // 2 * 2
        if width >= 100 and height >= 100:
            return left, top, width, height
    except Exception:
        pass
    return None


def _record_desktop_sync(
    plan: DesktopPlan, waits_ms: List[int], work_dir: str, token: str = ""
) -> Tuple[str, List[str]]:
    """対象ウィンドウの画面領域を録画しつつ自動操作する（同期）。

    gdigrab の title 指定は DWM 合成の最新アプリで黒画面になりがちなため、
    合成済みデスクトップから「ウィンドウの領域」を切り出して録画する。
    領域が取れない場合はデスクトップ全体を録画（フォールバック）。
    """
    from pywinauto import Desktop

    warnings: List[str] = []
    total_s = sum(waits_ms) / 1000 + 1.2

    win = None
    region: Tuple[int, int, int, int] | None = None
    try:
        win = Desktop(backend="uia").window(title=plan.window_title)
        win.wait("visible", timeout=8)
        win.set_focus()
        time.sleep(0.4)
        try:
            win.set_focus()
        except Exception:
            pass
        region = _window_region(win)
    except Exception as e:
        warnings.append(
            f"対象ウィンドウ「{plan.window_title}」に接続できませんでした: {e}"
        )
    time.sleep(0.3)

    out = os.path.join(work_dir, "desk.mp4")
    base = [FFMPEG, "-y", "-f", "gdigrab", "-framerate", "15"]
    if region:
        left, top, width, height = region
        cmd = base + [
            "-offset_x", str(left), "-offset_y", str(top),
            "-video_size", f"{width}x{height}", "-t", f"{total_s:.1f}",
            "-i", "desktop", out,
        ]
    else:
        # 領域が取れない → デスクトップ全体を録画
        warnings.append("ウィンドウ領域を取得できず、画面全体を録画します。")
        cmd = base + ["-t", f"{total_s:.1f}", "-i", "desktop", out]

    rec = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
    )
    time.sleep(0.8)

    from .service import is_cancelled

    for i, st in enumerate(plan.steps):
        if is_cancelled(token):
            warnings.append("ユーザー操作によりキャンセルされました。")
            break
        if win is not None:
            try:
                win.set_focus()
                _do_desktop_action(win, st)
            except Exception as e:
                warnings.append(f"ステップ{i + 1}({st.action}) をスキップ: {e}")
        time.sleep(max(1.2, waits_ms[i] / 1000))

    try:
        rec.communicate(timeout=total_s + 20)  # パイプも排出（デッドロック回避）
    except Exception:
        rec.kill()
    if not os.path.exists(out) or _duration(out) <= 0:
        raise RuntimeError(
            "画面録画に失敗しました（対象ウィンドウが最小化・非表示になっていないか確認してください）"
        )
    return out, warnings


# ============================================================
# 実行（TTS→録画+操作→合成）
# ============================================================
async def run_desktop_autopilot(
    plan: DesktopPlan, voice: str, out_dir: str, subtitles: bool = True,
    token: str = "", narrate: bool = True,
) -> RunResponse:
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="aivc_dap_")
    warnings: List[str] = []

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

    video, rec_warn = await asyncio.to_thread(
        _record_desktop_sync, plan, waits_ms, work, token
    )
    from .service import clear_cancel

    clear_cancel(token)
    warnings.extend(rec_warn)

    srt_name = None
    if subtitles:
        srt_path = os.path.join(work, "sub.srt")
        if _build_srt(plan.steps, durations, srt_path):
            srt_name = "sub.srt"

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"AIVideoCraft_app_{ts}.mp4")
    await asyncio.to_thread(
        _finalize, work, video, audio_paths, out_path, srt_name
    )

    return RunResponse(
        video_path=out_path,
        duration_sec=round(_duration(out_path), 2),
        steps_run=len(plan.steps),
        warnings=warnings,
    )
