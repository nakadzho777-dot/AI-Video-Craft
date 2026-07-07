"""動画編集の適用（ffmpeg）.

カット（区間削除）・テロップ焼き込み・音量・縦動画化・書き出しを1本の
ffmpeg で適用する。自動編集・手動編集の両方から使う共通処理。
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

from ..autopilot.service import FFMPEG, _NO_WINDOW, _duration
from ..logging_conf import get_logger

logger = get_logger(__name__)

_TELOP_STYLE_BASE = (
    "Fontname=Meiryo,FontSize=26,PrimaryColour=&H0000FFFF&,"
    "OutlineColour=&H00000000&,BorderStyle=1,Outline=3,Shadow=1"
)


def _telop_style(top: bool = False) -> str:
    """テロップの見た目。字幕がある動画では上寄せ(Alignment=8)で被りを避ける。"""
    if top:
        return _TELOP_STYLE_BASE + ",Alignment=8,MarginV=40"   # 上中央
    return _TELOP_STYLE_BASE + ",MarginV=64"                    # 下中央（既定）


def extract_frames(video_path: str, n: int = 5, width: int = 768) -> List[bytes]:
    """動画から均等な位置の静止画(JPEGバイト列)を n 枚取り出す。AI画像解析用。"""
    if not os.path.exists(video_path):
        return []
    dur = _duration(video_path)
    if dur <= 0:
        times = [1.0]
    else:
        times = [dur * (i + 0.5) / n for i in range(n)]
    frames: List[bytes] = []
    for t in times:
        r = subprocess.run(
            [FFMPEG, "-ss", f"{t:.2f}", "-i", os.path.abspath(video_path),
             "-frames:v", "1", "-vf", f"scale={width}:-1", "-f", "mjpeg", "pipe:1"],
            capture_output=True, creationflags=_NO_WINDOW,
        )
        if r.returncode == 0 and r.stdout:
            frames.append(r.stdout)
    return frames


def extract_frame_at(video_path: str, time_sec: float, width: int = 1280) -> bytes:
    """動画の指定秒のフレームを1枚 JPEG バイト列で取り出す（サムネのベース用）。"""
    if not os.path.exists(video_path):
        return b""
    t = max(0.0, float(time_sec))
    r = subprocess.run(
        [FFMPEG, "-ss", f"{t:.2f}", "-i", os.path.abspath(video_path),
         "-frames:v", "1", "-vf", f"scale={width}:-1", "-q:v", "2",
         "-f", "mjpeg", "pipe:1"],
        capture_output=True, creationflags=_NO_WINDOW,
    )
    return r.stdout if r.returncode == 0 and r.stdout else b""


def _merge(ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """区間をソート・マージ（重なり/近接を統合）。"""
    rs = sorted((max(0.0, s), e) for s, e in ranges if e > s)
    out: List[Tuple[float, float]] = []
    for s, e in rs:
        if out and s <= out[-1][1] + 0.05:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _srt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _bgr(hexs: str, default: str = "FFFFFF") -> str:
    """#RRGGBB → ASSのBBGGRR。"""
    h = (hexs or "").lstrip("#")
    if len(h) == 6:
        return (h[4:6] + h[2:4] + h[0:2]).upper()
    return default


def _ass_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


_ASS_HEADER = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n"
    "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
    "OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginV\n"
    "Style: Default,Meiryo,54,&H00FFFFFF,&H00000000,1,3,1,5,0\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Text\n"
)


def _telop_timing(
    telops: List[dict], dur: float, min_dur: float, gap: float
) -> List[dict]:
    """被り回避＋一瞬すぎる詰め込み防止のタイミングを算出（テキストありのみ）。"""
    items = sorted(
        [tp for tp in telops if str(tp.get("text", "")).strip()],
        key=lambda x: float(x["time_sec"]),
    )
    kept: List[dict] = []
    for tp in items:
        t = float(tp["time_sec"])
        if kept and t < kept[-1]["start"] + min_dur + gap:
            continue
        if kept and kept[-1]["end"] > t - gap:
            kept[-1]["end"] = t - gap
        kept.append({"start": t, "end": t + dur, "tp": tp})
    for k in kept:
        if k["end"] - k["start"] < min_dur:
            k["end"] = k["start"] + min_dur
    return kept


def _telop_ass(
    telops: List[dict],
    path: str,
    default_top: bool = False,
    dur: float = 2.8,
    min_dur: float = 1.2,
    gap: float = 0.12,
) -> bool:
    """テロップを ASS で書き出す（行ごとに色/サイズ/位置/アニメを反映）。"""
    kept = _telop_timing(telops, dur, min_dur, gap)
    lines = [_ASS_HEADER]
    for k in kept:
        tp = k["tp"]
        text = str(tp["text"]).strip().replace("\n", "\\N").replace("{", "").replace("}", "")
        size = int(tp.get("size") or 54)
        fill = _bgr(tp.get("color", "#ffffff"))
        outline = _bgr(tp.get("stroke", "#000000"), "000000")
        bold = 1 if tp.get("bold", True) else 0
        x = float(tp.get("x", 0.5) if tp.get("x") is not None else 0.5)
        yv = tp.get("y")
        y = float(yv) if yv is not None else (0.15 if default_top else 0.86)
        px, py = x * 1280, y * 720
        base = (
            f"\\an5\\fs{size}\\1c&H{fill}&\\3c&H{outline}&\\bord3\\shad1\\b{bold}"
        )
        anim = str(tp.get("anim", "none"))
        if anim == "pop":
            ov = (
                f"{base}\\pos({px:.0f},{py:.0f})"
                f"\\fscx55\\fscy55\\t(0,200,\\fscx100\\fscy100)\\fad(120,120)"
            )
        elif anim == "slide":
            ov = f"{base}\\move({px:.0f},{py + 90:.0f},{px:.0f},{py:.0f},0,260)\\fad(120,120)"
        elif anim == "fade":
            ov = f"{base}\\pos({px:.0f},{py:.0f})\\fad(260,260)"
        else:
            ov = f"{base}\\pos({px:.0f},{py:.0f})"
        lines.append(
            f"Dialogue: 0,{_ass_ts(k['start'])},{_ass_ts(k['end'])},Default,{{{ov}}}{text}"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(kept) > 0


def _telop_srt(
    telops: List[dict],
    path: str,
    dur: float = 2.8,
    min_dur: float = 1.2,
    gap: float = 0.12,
) -> None:
    """テロップSRTを作る。次の2点を守る:

    - テロップ同士が被らない（前のテロップは次の開始直前で終わる）。
    - 一瞬すぎるテロップを出さない（前と近すぎるものはスキップ＝詰め込み防止）。
      各テロップは最低 min_dur 秒は表示される。
    """
    items = sorted(
        [tp for tp in telops if str(tp.get("text", "")).strip()],
        key=lambda x: float(x["time_sec"]),
    )
    kept: List[list] = []  # [start, end, text]
    for tp in items:
        t = float(tp["time_sec"])
        text = str(tp["text"]).strip()
        # 直前に採用したテロップと近すぎる → 詰め込み防止でスキップ
        if kept and t < kept[-1][0] + min_dur + gap:
            continue
        # 直前のテロップの終わりを、このテロップの開始直前まで詰める（被り回避）
        if kept and kept[-1][1] > t - gap:
            kept[-1][1] = t - gap
        kept.append([t, t + dur, text])

    lines = []
    for i, (s, e, text) in enumerate(kept):
        if e - s < min_dur:            # 念のため最終チェック
            e = s + min_dur
        lines.append(f"{i + 1}\n{_srt_ts(s)} --> {_srt_ts(e)}\n{text}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _apply_sync(
    inp: str,
    out: str,
    cuts: List[Tuple[float, float]],
    telops: List[dict],
    vertical: bool,
    volume: float,
    mute: bool,
    work: str,
    telops_top: bool = False,
    speed: float = 1.0,
    vfilter: str = "none",
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> None:
    cuts = _merge(cuts or [])
    out_dur = _fx_out_dur(inp, cuts, speed)
    needs_cfr = bool(cuts) or abs((speed or 1.0) - 1.0) > 0.01
    vf: List[str] = []

    # カット/速度変更時は可変フレームレートだと音ズレするので、先に元FPSでCFR化
    if needs_cfr:
        vf.append(f"fps={_fps(inp):.3f}")
    if telops:
        _telop_ass(telops, os.path.join(work, "telop.ass"), default_top=telops_top)
        vf.append("subtitles=telop.ass")
    if vertical:
        vf.append(
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
        )
    if cuts:
        expr = "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in cuts)
        vf.append(f"select='not({expr})'")
        vf.append("setpts=N/FRAME_RATE/TB")
    vf += _fx_vsteps(vfilter, speed, fade_in, fade_out, out_dur)

    cmd = [FFMPEG, "-y", "-i", os.path.abspath(inp)]
    if vf:
        cmd += ["-vf", ",".join(vf)]

    if mute:
        cmd += ["-an"]
    else:
        af: List[str] = []
        if cuts:
            expr = "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in cuts)
            af += [f"aselect='not({expr})'", "asetpts=N/SR/TB"]
        if abs(volume - 1.0) > 0.01:
            af.append(f"volume={volume:.2f}")
        af.append("aresample=async=1")  # A/Vずれを補正
        af += _fx_asteps(speed, fade_in, fade_out, out_dur)
        cmd += ["-af", ",".join(af), "-c:a", "aac", "-ar", "48000"]

    cmd += ["-vsync", "cfr", *_ENC_VIDEO, out]
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=work, creationflags=_NO_WINDOW
    )
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"編集の適用に失敗しました: {r.stderr[-400:]}")


def _has_audio(path: str) -> bool:
    r = subprocess.run(
        [FFMPEG, "-i", path], capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    return "Audio:" in r.stderr


def _fps(path: str) -> float:
    """入力のフレームレートを取得（可変フレームレート対策の CFR 化に使う）。"""
    r = subprocess.run(
        [FFMPEG, "-i", path], capture_output=True, text=True, creationflags=_NO_WINDOW
    )
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", r.stderr)
    try:
        f = float(m.group(1)) if m else 30.0
    except (TypeError, ValueError):
        f = 30.0
    return f if 1.0 <= f <= 120.0 else 30.0


# 画質・A/Vずれ対策の共通エンコード設定（crf低め＝高画質、mediumで圧縮効率↑）
_ENC_VIDEO = [
    "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
    "-crf", "18", "-movflags", "+faststart",
]

# 色味フィルタのプリセット（フロントの選択肢と対応）
_FILTERS = {
    "none": "",
    "vivid": "eq=saturation=1.45:contrast=1.08",
    "mono": "hue=s=0",
    "warm": "colorbalance=rm=0.12:gm=0.03:bm=-0.10",
    "cool": "colorbalance=rm=-0.10:gm=0.0:bm=0.12",
    "retro": "curves=preset=vintage",
    "bright": "eq=brightness=0.08:saturation=1.1",
    "cinema": "eq=contrast=1.12:saturation=0.92",
}


def _fx_out_dur(inp: str, cuts, speed: float) -> float:
    """速度・カット適用後のおおよその出力尺（フェードアウト位置の計算用）。"""
    cut = sum(max(0.0, e - s) for s, e in (cuts or []))
    return max(0.1, (_duration(inp) - cut) / max(0.25, speed or 1.0))


def _fx_vsteps(vfilter: str, speed: float, fade_in: float, fade_out: float, out_dur: float):
    """色フィルタ・再生速度・フェードの映像フィルタ列を返す。"""
    s: List[str] = []
    f = _FILTERS.get(vfilter or "none", "")
    if f:
        s.append(f)
    if speed and abs(speed - 1.0) > 0.01:
        s.append(f"setpts={1.0 / speed:.4f}*PTS")
    if fade_in and fade_in > 0.01:
        s.append(f"fade=t=in:st=0:d={fade_in:.2f}")
    if fade_out and fade_out > 0.01:
        s.append(f"fade=t=out:st={max(0.0, out_dur - fade_out):.2f}:d={fade_out:.2f}")
    return s


def _fx_asteps(speed: float, fade_in: float, fade_out: float, out_dur: float):
    """再生速度(atempo)・フェードの音声フィルタ列を返す。"""
    s: List[str] = []
    if speed and abs(speed - 1.0) > 0.01:
        s.append(f"atempo={min(2.0, max(0.5, speed)):.4f}")
    if fade_in and fade_in > 0.01:
        s.append(f"afade=t=in:st=0:d={fade_in:.2f}")
    if fade_out and fade_out > 0.01:
        s.append(f"afade=t=out:st={max(0.0, out_dur - fade_out):.2f}:d={fade_out:.2f}")
    return s


def _pos_expr(pos: str) -> str:
    return {
        "tr": "W-w-24:24", "tl": "24:24", "br": "W-w-24:H-h-24",
        "bl": "24:H-h-24", "center": "(W-w)/2:(H-h)/2",
    }.get(pos, "W-w-24:24")


def _apply_materials(
    inp, out, cuts, telops, vertical, volume, mute, bgm, bgm_vol, overlays, work,
    telops_top=False, speed=1.0, vfilter="none", fade_in=0.0, fade_out=0.0,
) -> None:
    """素材（BGM/画像）を含む編集を filter_complex で一括適用。"""
    cuts = _merge(cuts or [])
    out_dur = _fx_out_dur(inp, cuts, speed)
    needs_cfr = bool(cuts) or abs((speed or 1.0) - 1.0) > 0.01
    has_audio = _has_audio(inp)
    inputs = ["-i", os.path.abspath(inp)]
    for ov in overlays:
        inputs += ["-i", os.path.abspath(ov["image"])]
    bgm_idx = None
    if bgm and not mute:
        # BGMを（速度・カット適用後の）出力尺ぶんだけループした有限ファイルに
        fit_sec = out_dur + 1.0
        bgm_fit = os.path.join(work, "bgm_fit.m4a")
        subprocess.run(
            [FFMPEG, "-y", "-stream_loop", "-1", "-i", os.path.abspath(bgm),
             "-t", f"{fit_sec:.2f}", "-c:a", "aac", bgm_fit],
            capture_output=True, creationflags=_NO_WINDOW,
        )
        inputs += ["-i", bgm_fit]
        bgm_idx = 1 + len(overlays)

    fc: List[str] = []
    steps: List[str] = []
    if needs_cfr:
        steps.append(f"fps={_fps(inp):.3f}")  # カット/速度時のCFR化（音ズレ防止）
    if telops:
        _telop_ass(telops, os.path.join(work, "telop.ass"), default_top=telops_top)
        steps.append("subtitles=telop.ass")
    if vertical:
        steps.append(
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
        )
    if cuts:
        expr = "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in cuts)
        steps += [f"select='not({expr})'", "setpts=N/FRAME_RATE/TB"]
    steps += _fx_vsteps(vfilter, speed, fade_in, fade_out, out_dur)
    fc.append(f"[0:v]{','.join(steps) if steps else 'null'}[vb]")

    prev = "[vb]"
    for i, ov in enumerate(overlays):
        fc.append(f"[{i + 1}:v]scale=420:-1[ovs{i}]")
        s = float(ov.get("start_sec", 0) or 0)
        e = float(ov.get("end_sec", 0) or 0)
        pos = _pos_expr(ov.get("position", "tr"))
        enable = f":enable='between(t\\,{s:.3f}\\,{e:.3f})'" if e > s else ""
        fc.append(f"{prev}[ovs{i}]overlay={pos}{enable}[v{i}]")
        prev = f"[v{i}]"
    vmap = prev

    amap = None
    if not mute:
        a_labels: List[str] = []
        if has_audio:
            asteps: List[str] = []
            if cuts:
                expr = "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in cuts)
                asteps += [f"aselect='not({expr})'", "asetpts=N/SR/TB"]
            if abs(volume - 1.0) > 0.01:
                asteps.append(f"volume={volume:.2f}")
            asteps.append("aresample=async=1")  # A/Vずれ補正
            asteps += _fx_asteps(speed, fade_in, fade_out, out_dur)
            fc.append(f"[0:a]{','.join(asteps)}[ab]")
            a_labels.append("[ab]")
        if bgm_idx is not None:
            fc.append(f"[{bgm_idx}:a]volume={bgm_vol:.2f}[bgmv]")
            a_labels.append("[bgmv]")
        if len(a_labels) >= 2:
            fc.append(
                f"{''.join(a_labels)}amix=inputs={len(a_labels)}:"
                "duration=first:dropout_transition=0[ao]"
            )
            amap = "[ao]"
        elif len(a_labels) == 1:
            amap = a_labels[0]

    cmd = [FFMPEG, "-y"] + inputs + ["-filter_complex", ";".join(fc), "-map", vmap]
    if mute:
        cmd += ["-an"]
    elif amap:
        cmd += ["-map", amap, "-c:a", "aac", "-ar", "48000"]
    cmd += ["-vsync", "cfr", *_ENC_VIDEO]
    if bgm_idx is not None:
        cmd += ["-shortest"]
    cmd += [out]
    r = subprocess.run(
        cmd, capture_output=True, text=True, cwd=work, creationflags=_NO_WINDOW
    )
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"編集の適用に失敗しました: {r.stderr[-500:]}")


async def apply_edit(
    inp: str,
    out_dir: str,
    *,
    cuts: Optional[List[Tuple[float, float]]] = None,
    telops: Optional[List[dict]] = None,
    vertical: bool = False,
    volume: float = 1.0,
    mute: bool = False,
    bgm: Optional[str] = None,
    bgm_volume: float = 0.3,
    overlays: Optional[List[dict]] = None,
    name: Optional[str] = None,
    subtitles: bool = False,
    speed: float = 1.0,
    vfilter: str = "none",
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> Tuple[str, float]:
    """編集を適用して MP4 を書き出す。(出力パス, 尺秒) を返す。

    subtitles=True（動画に字幕がある）なら、テロップを上寄せにして字幕との被りを避ける。
    speed=再生速度倍率, vfilter=色フィルタ名, fade_in/out=開始/終了フェード秒。
    """
    if not os.path.exists(inp):
        raise RuntimeError("元動画が見つかりません。")
    overlays = overlays or []
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="aivc_edit_")
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.abspath(os.path.join(out_dir, name or f"AIVideoCraft_edited_{ts}.mp4"))
    if bgm or overlays:
        await asyncio.to_thread(
            _apply_materials, inp, out, cuts or [], telops or [], vertical,
            volume, mute, bgm, bgm_volume, overlays, work, subtitles,
            speed, vfilter, fade_in, fade_out,
        )
    else:
        await asyncio.to_thread(
            _apply_sync, inp, out, cuts or [], telops or [], vertical, volume, mute,
            work, subtitles, speed, vfilter, fade_in, fade_out,
        )
    return out, round(_duration(out), 2)
