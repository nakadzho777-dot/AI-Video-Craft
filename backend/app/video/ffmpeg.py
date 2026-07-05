"""FFmpeg ラッパー.

「動画処理機能は交換・追加しやすいインターフェース設計」に従い、
編集機能（カット・結合・音量調整・縦動画化・書き出し等）を
この抽象の上に段階的に実装していく。

初期段階では最小限（バージョン確認・情報取得・カット）を提供する。
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)


class FFmpegError(RuntimeError):
    """FFmpeg 実行時エラー。"""


@dataclass
class MediaInfo:
    duration_sec: float
    width: int | None
    height: int | None
    raw: dict


@dataclass
class SilenceRange:
    """無音区間。"""

    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


class FFmpegService:
    """FFmpeg / FFprobe をサブプロセスで呼び出すサービス。"""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or get_settings().ffmpeg_path
        # ffprobe は ffmpeg と同ディレクトリ or PATH 上を想定
        self.ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")

    async def _run(self, args: list[str]) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout, stderr

    async def is_available(self) -> bool:
        try:
            code, _, _ = await self._run([self.ffmpeg_path, "-version"])
            return code == 0
        except (FileNotFoundError, OSError):
            return False

    async def probe(self, input_path: str | Path) -> MediaInfo:
        """メディア情報を取得する（ffprobe）。"""
        args = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ]
        code, out, err = await self._run(args)
        if code != 0:
            raise FFmpegError(err.decode("utf-8", "ignore"))
        data = json.loads(out.decode("utf-8", "ignore"))

        duration = float(data.get("format", {}).get("duration", 0.0))
        width = height = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                break
        return MediaInfo(duration_sec=duration, width=width, height=height, raw=data)

    async def cut(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        start_sec: float,
        end_sec: float,
    ) -> Path:
        """指定区間を切り出す（再エンコードなしのストリームコピー）。"""
        output_path = Path(output_path)
        args = [
            self.ffmpeg_path,
            "-y",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", str(input_path),
            "-c", "copy",
            str(output_path),
        ]
        code, _, err = await self._run(args)
        if code != 0:
            raise FFmpegError(err.decode("utf-8", "ignore"))
        return output_path

    async def detect_silence(
        self,
        input_path: str | Path,
        *,
        noise_db: float = -30.0,
        min_silence_sec: float = 0.5,
    ) -> list[SilenceRange]:
        """無音区間を検出する（silencedetect フィルタ）。

        無音検出はカット候補の抽出に使う（AIより正確）。
        """
        args = [
            self.ffmpeg_path,
            "-hide_banner",
            "-i", str(input_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_sec}",
            "-f", "null",
            "-",
        ]
        code, _, err = await self._run(args)
        stderr = err.decode("utf-8", "ignore")
        # silencedetect 情報が出ていれば returncode に関わらず解析する
        if code != 0 and "silence_" not in stderr:
            raise FFmpegError(stderr)
        return self._parse_silence(stderr)

    @staticmethod
    def _parse_silence(stderr: str) -> list[SilenceRange]:
        """ffmpeg stderr から silence_start / silence_end を抽出する。"""
        starts = [float(x) for x in re.findall(r"silence_start:\s*([-\d.]+)", stderr)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([-\d.]+)", stderr)]
        ranges: list[SilenceRange] = []
        for i, start in enumerate(starts):
            if i < len(ends):
                ranges.append(SilenceRange(start_sec=start, end_sec=ends[i]))
        return ranges

    async def set_volume(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        factor: float,
    ) -> Path:
        """音量を factor 倍に調整する（1.0=等倍）。"""
        output_path = Path(output_path)
        args = [
            self.ffmpeg_path, "-y",
            "-i", str(input_path),
            "-filter:a", f"volume={factor}",
            "-c:v", "copy",
            str(output_path),
        ]
        code, _, err = await self._run(args)
        if code != 0:
            raise FFmpegError(err.decode("utf-8", "ignore"))
        return output_path

    async def to_vertical(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        """縦動画化する（9:16 に中央クロップ + スケール）。"""
        output_path = Path(output_path)
        # 出力アスペクトに合わせて中央を埋め、はみ出しをクロップする
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
        args = [
            self.ffmpeg_path, "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-c:a", "copy",
            str(output_path),
        ]
        code, _, err = await self._run(args)
        if code != 0:
            raise FFmpegError(err.decode("utf-8", "ignore"))
        return output_path

    async def export(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        height: int | None = None,
        crf: int = 20,
    ) -> Path:
        """書き出し（任意で解像度変更 + H.264 再エンコード）。"""
        output_path = Path(output_path)
        args = [self.ffmpeg_path, "-y", "-i", str(input_path)]
        if height is not None:
            args += ["-vf", f"scale=-2:{height}"]
        args += [
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            "-c:a", "aac",
            str(output_path),
        ]
        code, _, err = await self._run(args)
        if code != 0:
            raise FFmpegError(err.decode("utf-8", "ignore"))
        return output_path
