"""IndexTTS2 local cost: ceil(duration_s) × $0.002 × USD_TO_CNY."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from magicdub_cli import constants as C
from magicdub_cli.adapters.tts.fal_index_tts_2 import _cost_cny_from_generated
from magicdub_cli.errors import USD_TO_CNY
from magicdub_cli.ffmpeg_util import audio_duration_s
from magicdub_cli.state.io import apply_adapter_cost, new_state, new_task_id


def _write_silence_wav(path: Path, *, seconds: float, rate: int = 16000) -> None:
    nframes = int(round(seconds * rate))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)


def test_audio_duration_s_wave(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    _write_silence_wav(path, seconds=1.25)
    assert abs(audio_duration_s(path) - 1.25) < 1e-6


def test_index_tts_cost_ceil(tmp_path: Path) -> None:
    path = tmp_path / "tts.wav"
    _write_silence_wav(path, seconds=1.25)
    # ceil(1.25) = 2 → 2 * 0.002 * 7 = 0.028
    assert _cost_cny_from_generated(path) == round(2 * C.INDEX_TTS_USD_PER_SEC * USD_TO_CNY, 8)


def test_index_tts_cost_exact_second(tmp_path: Path) -> None:
    path = tmp_path / "tts.wav"
    _write_silence_wav(path, seconds=3.0)
    assert _cost_cny_from_generated(path) == round(3 * C.INDEX_TTS_USD_PER_SEC * USD_TO_CNY, 8)
    assert math.ceil(3.0) == 3


def test_apply_adapter_cost_buckets() -> None:
    state = new_state(
        task_id=new_task_id(),
        title="c",
        src_language="en",
        tgt_language="zh-Hans",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={
            "sep": {"order": ["fal/demucs"]},
            "asr": {"order": ["fal/whisper"]},
            "translation": {"order": ["deepseek/deepseek-flash"]},
            "tts": {"order": ["fal/index-tts-2"]},
        },
    )
    apply_adapter_cost(state, "cost_of_tts", 0.028)
    apply_adapter_cost(state, "cost_of_tts", 0.014)
    apply_adapter_cost(state, "cost_of_sep", None)
    assert state["assets"]["cost"]["cost_of_tts"] == 0.042
    assert state["assets"]["cost"]["total"] == 0.042
