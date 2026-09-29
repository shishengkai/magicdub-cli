"""Fitting-round helpers and translation prompt modes."""

from __future__ import annotations

from magicdub_cli.pipeline.runner import (
    apply_attempt_selection,
    closest_attempt,
    select_attempt,
    sentence_ids_for_attempt,
    unsettled_sentence_ids,
)
from magicdub_cli.state.io import empty_cost, new_state, new_task_id


def _base_state() -> dict:
    return new_state(
        task_id=new_task_id(),
        title="demo",
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


def test_empty_cost_has_no_duration_fitting_bucket() -> None:
    cost = empty_cost()
    assert "cost_of_duration_fitting" not in cost
    assert set(cost) == {
        "cost_of_sep",
        "cost_of_asr",
        "cost_of_translation",
        "cost_of_tts",
        "total",
    }


def test_round_selection_pass_and_rejected() -> None:
    state = _base_state()
    state["assets"]["sentences"] = [
        {
            "id": 1,
            "selected_attempt": None,
            "tgt": [
                {
                    "attempt": 1,
                    "text": "hello",
                    "fitting_ratio": 1.0,
                    "selection": None,
                }
            ],
        },
        {
            "id": 2,
            "selected_attempt": None,
            "tgt": [
                {
                    "attempt": 1,
                    "text": "long",
                    "fitting_ratio": 1.5,
                    "selection": None,
                }
            ],
        },
    ]
    assert apply_attempt_selection(state, sentence_id=1, attempt=1, lo=0.8, hi=1.2) == (
        "fitting_pass"
    )
    assert state["assets"]["sentences"][0]["selected_attempt"] == 1
    assert apply_attempt_selection(state, sentence_id=2, attempt=1, lo=0.8, hi=1.2) == ("rejected")
    assert state["assets"]["sentences"][1]["selected_attempt"] is None
    assert unsettled_sentence_ids(state) == [2]
    # Rejected sentence still has attempt-1 text; next pipeline step is batch translate
    # attempt 2, not re-TTS attempt 1.
    assert sentence_ids_for_attempt(state, 1) == [2]
    state["assets"]["sentences"][1]["tgt"].append(
        {"attempt": 2, "text": "shorter", "fitting_ratio": None, "selection": None}
    )
    assert sentence_ids_for_attempt(state, 2) == [2]


def test_forced_closest_attempt() -> None:
    sent = {
        "id": 1,
        "tgt": [
            {"attempt": 1, "fitting_ratio": 1.5, "selection": "rejected"},
            {"attempt": 2, "fitting_ratio": 1.25, "selection": "rejected"},
            {"attempt": 3, "fitting_ratio": 0.5, "selection": "rejected"},
        ],
    }
    best = closest_attempt(sent, 0.8, 1.2)
    assert best == 2
    select_attempt(sent, best, "forced")
    assert sent["selected_attempt"] == 2
    assert sent["tgt"][1]["selection"] == "forced"
