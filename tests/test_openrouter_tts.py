"""OpenRouter Fish PCM→WAV helpers and paid cost (no live network)."""

from __future__ import annotations

import struct

import pytest

from magicdub_cli import constants as C
from magicdub_cli.adapters.tts.openrouter_fish_audio_s2_1_pro import _cost_cny_from_text
from magicdub_cli.errors import USD_TO_CNY, AdapterError
from magicdub_cli.openrouter_tts import attribution_headers, pcm_to_wav


def test_attribution_includes_title_and_referer() -> None:
    h = attribution_headers()
    assert h.get("X-OpenRouter-Title") == "MagicDub"
    assert h.get("X-Title") == "MagicDub"
    assert h.get("HTTP-Referer") == "https://magicdub.com"
    assert h.get("X-OpenRouter-Categories") == "audio-gen,video-gen"


def test_pcm_to_wav_mono() -> None:
    # 4 frames mono PCM16
    pcm = b"\x00\x00\x01\x00\x02\x00\x03\x00"
    wav = pcm_to_wav(pcm, "audio/pcm;rate=16000;channels=1")
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert struct.unpack_from("<I", wav, 24)[0] == 16000
    assert struct.unpack_from("<H", wav, 22)[0] == 1


def test_pcm_to_wav_rejects_bad_ctype() -> None:
    with pytest.raises(AdapterError):
        pcm_to_wav(b"\x00\x00", "audio/wav")


def test_openrouter_paid_cost() -> None:
    text = "hi"  # 2 bytes
    assert _cost_cny_from_text(text) == round(
        2 * C.FISH_S21_PRO_USD_PER_UTF8_BYTE * USD_TO_CNY, 8
    )
