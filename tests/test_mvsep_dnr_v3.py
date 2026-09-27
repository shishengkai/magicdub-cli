"""Unit tests for mvsep/dnr-v3 helpers (no live network)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from magicdub_cli import constants as C
from magicdub_cli.adapters.sep import mvsep_dnr_v3 as m
from magicdub_cli.errors import USD_TO_CNY, AdapterError


def test_api_ok_accepts_string_true() -> None:
    assert m._api_ok(True) is True
    assert m._api_ok("true") is True
    assert m._api_ok("True") is True
    assert m._api_ok("1") is True
    assert m._api_ok(1) is True
    assert m._api_ok(False) is False
    assert m._api_ok("false") is False
    assert m._api_ok(None) is False


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


def test_choose_output_format_from_stream() -> None:
    assert m.choose_output_format_from_stream({"codec_name": "mp3"}) == m.OUTPUT_MP3_320
    assert m.choose_output_format_from_stream({"codec_name": "aac"}) == m.OUTPUT_M4A
    assert m.choose_output_format_from_stream({"codec_name": "opus"}) == m.OUTPUT_M4A
    assert (
        m.choose_output_format_from_stream({"codec_name": "pcm_s16le", "sample_fmt": "s16"})
        == m.OUTPUT_FLAC_16
    )
    assert (
        m.choose_output_format_from_stream(
            {"codec_name": "flac", "bits_per_raw_sample": "24"}
        )
        == m.OUTPUT_FLAC_24
    )
    assert (
        m.choose_output_format_from_stream({"codec_name": "pcm_f32le", "sample_fmt": "fltp"})
        == m.OUTPUT_WAV_32
    )
    assert m.choose_output_format_from_stream({"codec_name": "flac"}) == m.OUTPUT_FLAC_16
    assert m.choose_output_format_from_stream({}) == m.OUTPUT_FLAC_16


def test_choose_output_format_probes_wav(tmp_path: Path) -> None:
    path = tmp_path / "s16.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 800)
    assert m.choose_output_format(path) == m.OUTPUT_FLAC_16


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


def test_remote_done_hash_from_data() -> None:
    body = {
        "success": True,
        "status": "done",
        "data": {
            "hash": "final-sep-hash",
            "link": "https://mvsep.com/api/separation/get?hash=final-sep-hash",
        },
    }
    assert m._remote_done_hash(body, "remote") == "final-sep-hash"


def test_remote_done_hash_from_link_only() -> None:
    body = {
        "success": True,
        "status": "done",
        "data": {"link": "https://mvsep.com/api/separation/get?hash=from-link"},
    }
    assert m._remote_done_hash(body, "remote") == "from-link"


def test_remote_done_hash_missing_raises() -> None:
    with pytest.raises(AdapterError):
        m._remote_done_hash({"success": True, "status": "done", "data": {}}, "remote")


def test_mvsep_credits_floor_minutes() -> None:
    # Empirically: 119s → 1 credit, 121s → 2 credits (floor minutes).
    assert m.credits_from_duration_s(119.0) == 1
    assert m.credits_from_duration_s(121.0) == 2
    assert m.credits_from_duration_s(60.0) == 1
    assert m.credits_from_duration_s(59.9) == 0
    assert m.credits_from_duration_s(0.0) == 0


def test_mvsep_cost_per_credit_025_usd() -> None:
    assert C.MVSEP_CREDITS_PER_MINUTE == 1
    assert C.MVSEP_USD_PER_CREDIT == 0.025
    # 1 credit × $0.025 × 7 = ¥0.175
    assert m._cost_cny_from_credits(1) == round(0.025 * USD_TO_CNY, 8)
    assert m._cost_cny_from_credits(1) == 0.175
    # 2 credits (e.g. 121s) → ¥0.35
    assert m._cost_cny_from_credits(m.credits_from_duration_s(121.0)) == 0.35
