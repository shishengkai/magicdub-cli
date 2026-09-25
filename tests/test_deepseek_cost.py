"""deepseek-flash local cost from usage × CNY pricing (no spend field in API)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from magicdub_cli.adapters.translation.deepseek_deepseek_flash import (
    _cost_from_usage,
    _is_peak,
    _rates_cny_per_m,
)

_SH = ZoneInfo("Asia/Shanghai")


def test_peak_weekday_morning() -> None:
    assert _is_peak(now=datetime(2026, 9, 25, 10, 0, tzinfo=_SH)) is True  # Thu


def test_idle_weekday_evening() -> None:
    assert _is_peak(now=datetime(2026, 9, 25, 20, 0, tzinfo=_SH)) is False


def test_idle_weekend() -> None:
    assert _is_peak(now=datetime(2026, 9, 26, 10, 0, tzinfo=_SH)) is False  # Sat


def test_idle_rates_half_of_peak() -> None:
    peak = _rates_cny_per_m(now=datetime(2026, 9, 25, 10, 0, tzinfo=_SH))
    idle = _rates_cny_per_m(now=datetime(2026, 9, 25, 20, 0, tzinfo=_SH))
    assert idle["cache_miss"] == peak["cache_miss"] * 0.5
    assert idle["output"] == peak["output"] * 0.5
    assert idle["cache_hit"] == peak["cache_hit"] * 0.5


def test_cost_idle_cache_miss_and_output() -> None:
    # 1M miss + 1M out at idle → 1 + 4 = 5 CNY
    now = datetime(2026, 9, 25, 20, 0, tzinfo=_SH)
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 1_000_000,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 1_000_000,
    }
    assert _cost_from_usage(usage, now=now) == 5.0


def test_cost_peak_with_cache_hit() -> None:
    # peak: 0.5M hit * 0.04 + 0.5M miss * 2 + 0.25M out * 8
    now = datetime(2026, 9, 25, 15, 0, tzinfo=_SH)
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 250_000,
        "prompt_cache_hit_tokens": 500_000,
        "prompt_cache_miss_tokens": 500_000,
    }
    expected = round(0.5 * 0.04 + 0.5 * 2.0 + 0.25 * 8.0, 8)
    assert _cost_from_usage(usage, now=now) == expected


def test_cost_fallback_all_prompt_as_miss() -> None:
    now = datetime(2026, 9, 25, 20, 0, tzinfo=_SH)
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    assert _cost_from_usage(usage, now=now) == 1.0


def test_cost_missing_tokens() -> None:
    assert _cost_from_usage({}) is None
    assert _cost_from_usage({"prompt_tokens": 10}) is None


def test_probe_sample_shape() -> None:
    """Matches live probe: no cost field; usage has cache hit/miss."""
    now = datetime(2026, 9, 24, 22, 0, tzinfo=_SH)  # idle
    usage = {
        "prompt_tokens": 78,
        "completion_tokens": 75,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 78,
    }
    # idle: 78/1e6 * 1 + 75/1e6 * 4
    expected = round(78 / 1_000_000 * 1.0 + 75 / 1_000_000 * 4.0, 8)
    assert _cost_from_usage(usage, now=now) == expected
