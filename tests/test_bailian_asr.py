"""Unit tests for Bailian ASR helpers and cost (no live network)."""

from __future__ import annotations

from magicdub_cli import constants as C
from magicdub_cli import bailian_asr as b
from magicdub_cli.adapters.asr.bailian_fun_asr import _cost_cny_duration
from magicdub_cli.adapters.asr.bailian_qwen_audio_3_1_asr_flash_filetrans import (
    _cost_cny_tokens,
)


def test_language_hints() -> None:
    assert b.language_hints("zh-Hans") == ["zh"]
    assert b.language_hints("en") == ["en"]
    assert b.language_hints(None) == []


def test_parse_sentences() -> None:
    body = {
        "transcripts": [
            {
                "content_duration_in_milliseconds": 2500,
                "sentences": [
                    {
                        "begin_time": 100,
                        "end_time": 900,
                        "text": "hello",
                        "speaker_id": 0,
                    },
                    {
                        "begin_time": 1000,
                        "end_time": 2000,
                        "text": "world",
                        "speaker_id": 1,
                    },
                ],
            }
        ]
    }
    text, sentences = b.parse_sentences(body)
    assert text == "hello world"
    assert sentences[0]["speaker_id"] == "0"
    assert sentences[1]["start_ms"] == 1000


def test_content_duration_and_fun_cost() -> None:
    tx = {
        "transcripts": [
            {"content_duration_in_milliseconds": 21000},
            {"content_duration_in_milliseconds": 2000},
        ]
    }
    assert b.content_duration_seconds(tx) == 23.0
    assert _cost_cny_duration(tx, {}) == round(23.0 * C.FUN_ASR_CNY_PER_SEC, 8)


def test_fun_cost_falls_back_to_usage_duration() -> None:
    assert _cost_cny_duration({}, {"usage": {"duration": 21}}) == round(
        21 * C.FUN_ASR_CNY_PER_SEC, 8
    )
    assert _cost_cny_duration({}, {}) is None


def test_qwen_token_cost() -> None:
    body = {"usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
    assert _cost_cny_tokens(body) == round(
        C.QWEN31_ASR_INPUT_CNY_PER_MTOK + C.QWEN31_ASR_OUTPUT_CNY_PER_MTOK, 8
    )
    assert _cost_cny_tokens({"usage": {}}) is None
    assert _cost_cny_tokens({}) is None


def test_extract_token_usage_aliases() -> None:
    assert b.extract_token_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 3}}
    ) == (10, 3)
