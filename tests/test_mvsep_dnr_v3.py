"""Unit tests for mvsep/dnr-v3 helpers (no live network)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from magicdub_cli import constants as C
from magicdub_cli.adapters.sep import mvsep_dnr_v3 as m
from magicdub_cli.errors import USD_TO_CNY, AdapterError


def test_ok_download_url() -> None:
    assert m._ok_download_url("https://mvsep.com/storage/foo/speech.wav") is True
    assert m._ok_download_url("https://sg.mvsep.com/storage/foo/speech.wav") is True
    assert m._ok_download_url("https://evil.com/storage/foo.wav") is False
    assert m._ok_download_url("https://mvsep.com/storage/foo.wav?x=1") is False


def test_stem_files_ignores_independent_extras() -> None:
    body = {
        "data": {
            "hash": "abc",
            "files": [
                {"type": "speech", "url": "https://mvsep.com/storage/a/speech.wav"},
                {"type": "music", "url": "https://mvsep.com/storage/a/music.wav"},
                {"type": "sfx", "url": "https://mvsep.com/storage/a/sfx.wav"},
                {"type": "mel_extra", "url": "https://mvsep.com/storage/a/extra.wav"},
            ],
        }
    }
    stems = m._stem_files(body, "abc")
    assert set(stems) == {"speech", "music", "sfx"}


def test_stem_files_missing_raises() -> None:
    body = {
        "data": {
            "hash": "abc",
            "files": [
                {"type": "speech", "url": "https://mvsep.com/storage/a/speech.wav"},
            ],
        }
    }
    with pytest.raises(AdapterError):
        m._stem_files(body, "abc")


def test_mix_music_sfx(tmp_path: Path) -> None:
    def _write_silence(path: Path, frames: int = 800) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * frames)

    music = tmp_path / "music.wav"
    sfx = tmp_path / "sfx.wav"
    _write_silence(music)
    _write_silence(sfx)
    out = m._mix_music_sfx(music, sfx, tmp_path / "non_speech.wav")
    assert out.is_file()
    assert out.stat().st_size > 0


def test_mvsep_cost_one_credit_at_zero_usd() -> None:
    # 1 credit × $0.00 × 7 = 0
    assert C.MVSEP_CREDITS_PER_JOB == 1
    assert C.MVSEP_USD_PER_CREDIT == 0.0
    assert m._cost_cny_from_credits(C.MVSEP_CREDITS_PER_JOB) == round(
        1 * C.MVSEP_USD_PER_CREDIT * USD_TO_CNY, 8
    )
    assert m._cost_cny_from_credits(1) == 0.0
