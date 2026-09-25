"""Remote download suffix follows URL／fal File metadata."""

from __future__ import annotations

from magicdub_cli.fal_api import suffix_from_remote


def test_suffix_from_url_mp3() -> None:
    assert (
        suffix_from_remote(
            url="https://storage.googleapis.com/falserverless/example_outputs/index-tts-2/tts_out.mp3"
        )
        == ".mp3"
    )


def test_suffix_from_content_type() -> None:
    assert (
        suffix_from_remote(
            url="https://example.com/files/abc",
            file_obj={"content_type": "audio/mpeg"},
        )
        == ".mp3"
    )


def test_suffix_from_file_name() -> None:
    assert (
        suffix_from_remote(
            url="https://example.com/files/abc",
            file_obj={"file_name": "vocals.wav"},
        )
        == ".wav"
    )
