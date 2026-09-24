"""ffmpeg / ffprobe helpers."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or f"ffmpeg failed: {cmd}")


def ffprobe_json(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or f"ffprobe failed: {path}")
    return json.loads(proc.stdout)


def audio_duration_s(path: Path) -> float:
    """Audio duration in seconds. Prefer stdlib ``wave`` for ``.wav``; else ffprobe."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                rate = wf.getframerate()
                if rate <= 0:
                    raise FFmpegError(f"invalid wav sample rate: {path}")
                return wf.getnframes() / float(rate)
        except wave.Error:
            pass
    return audio_duration_ms(path) / 1000.0


def audio_duration_ms(path: Path) -> int:
    data = ffprobe_json(path)
    # Prefer audio stream duration
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "audio" and stream.get("duration") is not None:
            return int(round(float(stream["duration"]) * 1000))
    fmt = data.get("format") or {}
    if fmt.get("duration") is not None:
        return int(round(float(fmt["duration"]) * 1000))
    raise FFmpegError(f"cannot determine duration: {path}")


def media_duration_ms(path: Path) -> int:
    data = ffprobe_json(path)
    fmt = data.get("format") or {}
    if fmt.get("duration") is not None:
        return int(round(float(fmt["duration"]) * 1000))
    raise FFmpegError(f"cannot determine duration: {path}")
