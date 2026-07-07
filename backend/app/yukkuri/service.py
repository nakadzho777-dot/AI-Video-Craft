"""ゆっくり解説サービス.

- 台本生成: AIプロバイダーで2キャラ掛け合い台本を構造化。
- 動画生成: 各セリフを音声合成→フレーム描画→クリップ化→連結でMP4に。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import PurePath
from typing import List

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..autopilot.service import FFMPEG, _NO_WINDOW, _duration
from ..logging_conf import get_logger
from .models import (
    CharacterConfig,
    RenderResponse,
    ScriptRequest,
    YukkuriLine,
    YukkuriScript,
)
from .prompts import (
    build_jikkyou_system_prompt,
    build_jikkyou_user_prompt,
    build_single_jikkyou_system_prompt,
    build_single_system_prompt,
    build_system_prompt,
    build_user_prompt,
)
from .render import render_frame, render_overlay
from .voice import synth_line

logger = get_logger(__name__)


class ScriptParseError(RuntimeError):
    """AI応答を台本として解釈できなかった。"""


# ============================================================
# 台本生成（AI）
# ============================================================
class YukkuriScriptService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate(self, req: ScriptRequest, *, model: str) -> YukkuriScript:
        single = req.speakers <= 1
        if req.mode == "jikkyou":
            target_lines = max(4, min(30, int((req.target_sec or 30) / 4.5)))
            system = (
                build_single_jikkyou_system_prompt(req.name_a)
                if single
                else build_jikkyou_system_prompt(req.name_a, req.name_b)
            )
            user = build_jikkyou_user_prompt(
                req.topic, req.notes, req.instructions, target_lines
            )
        else:
            system = (
                build_single_system_prompt(req.name_a)
                if single
                else build_system_prompt(req.name_a, req.name_b)
            )
            user = build_user_prompt(req.topic, req.notes, req.instructions)
            # 元動画がある場合は、その尺に合わせてセリフ本数を調整
            if req.target_sec and req.target_sec > 0:
                n = max(4, min(30, int(req.target_sec / 4.5)))
                user += (
                    f"\n\n※ 約{int(req.target_sec)}秒の動画に重ねます。"
                    f"セリフは {n} 本程度に収めてください。"
                )
        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.7
            )
        except JsonExtractError as e:
            raise ScriptParseError(str(e)) from e
        try:
            script = YukkuriScript.model_validate(data)
        except Exception as e:
            raise ScriptParseError(f"台本の形式が不正です: {e}") from e
        # speaker を a/b に正規化（1人モードは全て a）
        for ln in script.lines:
            if single or ln.speaker not in ("a", "b"):
                ln.speaker = "a"
        if not script.lines:
            raise ScriptParseError("セリフが生成されませんでした")
        return script


# ============================================================
# 動画生成
# ============================================================
def _make_clip(
    chars: CharacterConfig, line: YukkuriLine, audio: str, work: str, i: int
) -> str:
    """1セリフ分のクリップ（静止画＋音声）を作る。"""
    frame = os.path.join(work, f"f{i}.png")
    render_frame(chars, line, frame)
    clip = os.path.join(work, f"clip{i}.mp4")
    subprocess.run(
        [FFMPEG, "-y", "-loop", "1", "-i", frame, "-i", audio,
         "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "15",
         "-c:a", "aac", "-shortest", clip],
        capture_output=True, creationflags=_NO_WINDOW,
    )
    if not os.path.exists(clip) or _duration(clip) <= 0:
        raise RuntimeError(f"セリフ{i + 1} のクリップ生成に失敗しました")
    return clip


def _concat(clips: List[str], work: str, out_path: str) -> None:
    lst = os.path.join(work, "clips.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for c in clips:
            f.write("file '" + PurePath(c).as_posix() + "'\n")
    r = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", "-movflags", "+faststart", out_path],
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    )
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"動画の連結に失敗しました: {r.stderr[-300:]}")


async def render_video(
    script: YukkuriScript, chars: CharacterConfig, out_dir: str
) -> RenderResponse:
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="aivc_yk_")
    warnings: List[str] = []
    engine_used = "edge-tts"

    clips: List[str] = []
    for i, line in enumerate(script.lines):
        text = (line.text or "").strip()
        if not text:
            continue
        voice = chars.voice_a if line.speaker == "a" else chars.voice_b
        audio = os.path.join(work, f"a{i}.mp3")
        try:
            engine_used = await synth_line(text, voice, audio)
        except Exception as e:
            warnings.append(f"セリフ{i + 1} の音声合成に失敗: {e}")
            continue
        try:
            clip = await asyncio.to_thread(_make_clip, chars, line, audio, work, i)
            clips.append(clip)
        except Exception as e:
            warnings.append(f"セリフ{i + 1} の生成に失敗: {e}")

    if not clips:
        raise RuntimeError("有効なセリフがありませんでした")

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"AIVideoCraft_yukkuri_{ts}.mp4")
    await asyncio.to_thread(_concat, clips, work, out_path)

    return RenderResponse(
        video_path=out_path,
        duration_sec=round(_duration(out_path), 2),
        lines=len(clips),
        voice_engine=engine_used,
        warnings=warnings,
    )


# ============================================================
# ゆっくり実況（元動画にキャラ＋字幕＋実況音声を重ねる）
# ============================================================
def _srt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _has_audio(path: str) -> bool:
    r = subprocess.run(
        [FFMPEG, "-i", path], capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    return "Audio:" in r.stderr


_JK_STYLE = (
    "Fontname=Meiryo,FontSize=22,PrimaryColour=&H00FFFFFF&,"
    "OutlineColour=&H00000000&,BorderStyle=1,Outline=2,MarginV=30"
)


def _composite_jikkyou(base, overlay, commentary, srt_name, out_path, work, keep_audio):
    # 実況（解説音声）が元動画より長い場合、元動画の長さで切られて「予定より短い」
    # 動画になってしまう。実況が全部流れるよう、足りない分は最終フレームを保持して
    # 元動画を延長し、出力尺を max(元動画, 実況) にする。
    base_dur = _duration(base)
    comm_dur = _duration(commentary)
    total = max(base_dur, comm_dur)
    pad = max(0.0, comm_dur - base_dur)
    has_audio = keep_audio and _has_audio(base)

    vchain = "[0:v][1:v]overlay=0:0"
    if pad > 0.1:
        # 実況の残り時間ぶん、最後の画面を静止させて延長
        vchain += f",tpad=stop_mode=clone:stop_duration={pad:.2f}"
    vchain += "[v1]"
    if srt_name:
        vchain += f";[v1]subtitles={srt_name}:force_style='{_JK_STYLE}'[vout]"
        vmap = "[vout]"
    else:
        vmap = "[v1]"
    if has_audio:
        # 元動画の音を残しつつ実況をミックス（実況が終わるまで＝longest）
        achain = (
            ";[0:a]volume=0.35[a0];[a0][2:a]"
            "amix=inputs=2:duration=longest:dropout_transition=0[aout]"
        )
        amap = "[aout]"
    else:
        achain = ""
        amap = "2:a"
    cmd = [
        FFMPEG, "-y", "-i", os.path.abspath(base), "-i", overlay, "-i", commentary,
        "-filter_complex", vchain + achain, "-map", vmap, "-map", amap,
        "-t", f"{total:.2f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-movflags", "+faststart", out_path,
    ]
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=work, creationflags=_NO_WINDOW
    )
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"実況の合成に失敗しました: {r.stderr[-400:]}")


async def render_jikkyou(
    base_video, script, chars, voice_a, voice_b, out_dir, subtitles=True, keep_audio=True
) -> RenderResponse:
    if not os.path.exists(base_video):
        raise RuntimeError("元動画が見つかりません。")
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="aivc_jk_")
    warnings: List[str] = []
    engine = "edge-tts"

    audio_paths: List[str] = []
    srt_parts: List[str] = []
    t = 0.0
    idx = 1
    for i, line in enumerate(script.lines):
        text = (line.text or "").strip()
        if not text:
            continue
        voice = voice_a if line.speaker == "a" else voice_b
        name = chars.name_a if line.speaker == "a" else chars.name_b
        ap = os.path.join(work, f"a{i}.mp3")
        try:
            engine = await synth_line(text, voice, ap)
        except Exception as e:
            warnings.append(f"セリフ{i + 1} の音声合成に失敗: {e}")
            continue
        d = max(1.0, _duration(ap))
        srt_parts.append(
            f"{idx}\n{_srt_ts(t)} --> {_srt_ts(t + d)}\n{name}：{text}\n"
        )
        idx += 1
        audio_paths.append(ap)
        t += d
    if not audio_paths:
        raise RuntimeError("有効なセリフがありませんでした")

    # 実況音声を連結。voice_a/voice_b でエンジンが異なると mp3/wav が混在するため、
    # concat デムーサ(-c copy)ではなく concat フィルタで再エンコードして確実に繋ぐ。
    commentary = os.path.join(work, "comm.m4a")
    concat_cmd: List[str] = [FFMPEG, "-y"]
    for a in audio_paths:
        concat_cmd += ["-i", a]
    n = len(audio_paths)
    concat_cmd += [
        "-filter_complex", f"concat=n={n}:v=0:a=1[a]",
        "-map", "[a]", "-c:a", "aac", commentary,
    ]
    r = subprocess.run(
        concat_cmd, capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    if r.returncode != 0 or not os.path.exists(commentary) or _duration(commentary) <= 0:
        raise RuntimeError(f"実況音声の連結に失敗しました: {r.stderr[-300:]}")

    srt_name = None
    if subtitles and srt_parts:
        with open(os.path.join(work, "jk.srt"), "w", encoding="utf-8") as f:
            f.write("\n".join(srt_parts))
        srt_name = "jk.srt"

    overlay = os.path.join(work, "ov.png")
    await asyncio.to_thread(render_overlay, chars, overlay)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"AIVideoCraft_jikkyou_{ts}.mp4")
    await asyncio.to_thread(
        _composite_jikkyou, base_video, overlay, commentary, srt_name,
        out_path, work, keep_audio,
    )
    return RenderResponse(
        video_path=out_path,
        duration_sec=round(_duration(out_path), 2),
        lines=len(audio_paths),
        voice_engine=engine,
        warnings=warnings,
    )
