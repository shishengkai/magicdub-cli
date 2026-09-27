"""fixed:demux — stream-copy audio when possible."""

from __future__ import annotations

import subprocess
from pathlib import Path

from magicdub_cli.ffmpeg_util import ffprobe_json
from magicdub_cli.state.io import new_state, new_task_id
from magicdub_cli.steps.fixed.demux import copy_extension_for_codec
from magicdub_cli.steps.fixed.demux import run as demux_run


def _make_aac_mp4(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=0.4",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=0.4",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _make_pcm_wav_in_mkv(path: Path) -> None:
    """PCM in Matroska — copy target is .wav."""
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=0.3",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=0.3",
            "-c:a",
            "pcm_s16le",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_copy_extension_for_codec() -> None:
    assert copy_extension_for_codec("aac") == ".m4a"
    assert copy_extension_for_codec("AAC") == ".m4a"
    assert copy_extension_for_codec("opus") == ".opus"
    assert copy_extension_for_codec("pcm_s16le") == ".wav"
    assert copy_extension_for_codec("unknown_codec") is None
    assert copy_extension_for_codec(None) is None


def test_demux_copies_aac_to_m4a(tmp_path: Path) -> None:
    video = tmp_path / "media" / "src" / "video.mp4"
    video.parent.mkdir(parents=True)
    _make_aac_mp4(video)
    (tmp_path / "tmp").mkdir()

    state = new_state(
        task_id=new_task_id(),
        title="t",
        src_language="en",
        tgt_language="zh",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={
            "sep": {"order": ["fal/demucs"]},
            "asr": {"order": ["fal/whisper"]},
            "translation": {"order": ["deepseek/deepseek-flash"]},
            "tts": {"order": ["fal/index-tts-2"]},
        },
    )
    state["assets"]["src"]["video"] = {
        "path": "media/src/video.mp4",
        "sha256": "x",
        "size_bytes": video.stat().st_size,
    }

    result = demux_run(tmp_path, state)
    assert result.ok, result.message
    audio_rel = state["assets"]["src"]["audio"]["path"]
    assert audio_rel == "media/src/audio.m4a"
    audio = tmp_path / audio_rel
    assert audio.is_file()
    silent = tmp_path / state["assets"]["src"]["silent_video"]["path"]
    assert silent.is_file()

    streams = ffprobe_json(audio).get("streams") or []
    assert any(s.get("codec_name") == "aac" for s in streams)
    # Stream copy should stay far smaller than a float32 WAV of the same clip.
    assert audio.stat().st_size < 80_000


def test_demux_pcm_copies_to_wav(tmp_path: Path) -> None:
    video = tmp_path / "media" / "src" / "video.mkv"
    video.parent.mkdir(parents=True)
    _make_pcm_wav_in_mkv(video)
    (tmp_path / "tmp").mkdir()

    state = new_state(
        task_id=new_task_id(),
        title="t",
        src_language="en",
        tgt_language="zh",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={
            "sep": {"order": ["fal/demucs"]},
            "asr": {"order": ["fal/whisper"]},
            "translation": {"order": ["deepseek/deepseek-flash"]},
            "tts": {"order": ["fal/index-tts-2"]},
        },
    )
    state["assets"]["src"]["video"] = {
        "path": "media/src/video.mkv",
        "sha256": "x",
        "size_bytes": video.stat().st_size,
    }

    result = demux_run(tmp_path, state)
    assert result.ok, result.message
    assert state["assets"]["src"]["audio"]["path"] == "media/src/audio.wav"
    assert (tmp_path / "media/src/audio.wav").is_file()
