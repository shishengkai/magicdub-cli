"""fal Demucs local cost: ceil(audio_s) × $0.0007 × USD_TO_CNY."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from magicdub_cli import constants as C
from magicdub_cli.adapters.sep.fal_demucs import _cost_cny_from_audio_duration
from magicdub_cli.errors import USD_TO_CNY
from magicdub_cli.ffmpeg_util import audio_duration_s


def _write_silence_wav(path: Path, *, seconds: float, rate: int = 16000) -> None:
    nframes = int(round(seconds * rate))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)


def test_demucs_cost_ceil(tmp_path: Path) -> None:
    path = tmp_path / "in.wav"
    _write_silence_wav(path, seconds=1.25)
    assert abs(audio_duration_s(path) - 1.25) < 1e-6
    # ceil(1.25) = 2 → 2 * 0.0007 * 7 = 0.0098
    assert _cost_cny_from_audio_duration(1.25) == round(
        2 * C.DEMUCS_USD_PER_AUDIO_SEC * USD_TO_CNY, 8
    )
    assert math.ceil(1.25) == 2


def test_demucs_cost_exact_second() -> None:
    assert _cost_cny_from_audio_duration(60.0) == round(
        60 * C.DEMUCS_USD_PER_AUDIO_SEC * USD_TO_CNY, 8
    )
