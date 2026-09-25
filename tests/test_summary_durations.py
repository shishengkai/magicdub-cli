"""Finish-report duration helpers."""

from __future__ import annotations

from magicdub_cli.pipeline.runner import _format_duration_s, run_elapsed_s


def test_format_duration_s() -> None:
    assert _format_duration_s(0) == "0.0s"
    assert _format_duration_s(45.04) == "45.0s"
    assert _format_duration_s(90.2) == "1m 30.2s"
    assert _format_duration_s(3661.5) == "1h 1m 1.5s"


def test_run_elapsed_s() -> None:
    state = {
        "created_at": "2026-09-25T12:00:00+00:00",
        "run": {"steps": {"finish": {"finished_at": "2026-09-25T12:01:30.500000+00:00"}}},
    }
    assert run_elapsed_s(state) == 90.5
    assert (
        run_elapsed_s(
            {"created_at": "2026-09-25T12:00:00+00:00", "run": {"steps": {}}},
            ended_at="2026-09-25T12:00:05+00:00",
        )
        == 5.0
    )
    assert run_elapsed_s({}) is None
