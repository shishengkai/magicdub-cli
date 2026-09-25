"""Fish Instant clone helpers and paid cost (no live network)."""

from __future__ import annotations

import struct

import pytest

from magicdub_cli import constants as C
from magicdub_cli.adapters.tts.fishaudio_s2_1_pro import _cost_cny_from_text
from magicdub_cli.errors import USD_TO_CNY, AdapterError
from magicdub_cli.fish_tts import normalize_wav


def _minimal_pcm_wav(*, frames: int = 100) -> bytes:
    """44.1 kHz mono PCM16 WAV with correct sizes."""
    data = b"\x00\x00" * frames
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16)
    header += b"data" + struct.pack("<I", len(data)) + data
    return header


def test_normalize_wav_ok() -> None:
    raw = _minimal_pcm_wav()
    assert normalize_wav(raw) == raw


def test_normalize_wav_repairs_streaming_sizes() -> None:
    raw = bytearray(_minimal_pcm_wav(frames=50))
    struct.pack_into("<I", raw, 4, 0xFFFFFF24)
    struct.pack_into("<I", raw, 40, 0xFFFFFF00)
    fixed = normalize_wav(bytes(raw))
    assert struct.unpack_from("<I", fixed, 4)[0] == len(fixed) - 8
    assert struct.unpack_from("<I", fixed, 40)[0] == len(fixed) - 44


def test_normalize_wav_rejects_non_wav() -> None:
    with pytest.raises(AdapterError):
        normalize_wav(b"not-a-wav")


def test_paid_cost_utf8_bytes() -> None:
    text = "你好"  # 6 UTF-8 bytes
    assert len(text.encode("utf-8")) == 6
    assert _cost_cny_from_text(text) == round(
        6 * C.FISH_S21_PRO_USD_PER_UTF8_BYTE * USD_TO_CNY, 8
    )
