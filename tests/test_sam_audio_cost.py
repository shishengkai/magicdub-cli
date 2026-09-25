"""fal SAM Audio local cost: ceil(s/30) × $0.05 (+ rerank surcharge) × USD_TO_CNY."""

from __future__ import annotations

import math

from magicdub_cli import constants as C
from magicdub_cli.adapters.sep.fal_sam_audio import _cost_cny_from_output_duration
from magicdub_cli.errors import USD_TO_CNY


def test_sam_cost_one_unit() -> None:
    # 26.6s → 1 × 0.05 × 7
    assert _cost_cny_from_output_duration(26.6) == round(
        1 * C.SAM_AUDIO_USD_PER_30S * USD_TO_CNY, 8
    )


def test_sam_cost_two_units() -> None:
    # 30.1s → 2 × 0.05 × 7
    assert math.ceil(30.1 / 30.0) == 2
    assert _cost_cny_from_output_duration(30.1) == round(
        2 * C.SAM_AUDIO_USD_PER_30S * USD_TO_CNY, 8
    )


def test_sam_cost_extra_rerank() -> None:
    # candidates=3 → 1 base + 2 × $0.025 per 30s unit
    units = 1
    usd = units * C.SAM_AUDIO_USD_PER_30S + units * C.SAM_AUDIO_RERANK_USD_PER_30S * 2
    assert _cost_cny_from_output_duration(10.0, reranking_candidates=3) == round(
        usd * USD_TO_CNY, 8
    )
