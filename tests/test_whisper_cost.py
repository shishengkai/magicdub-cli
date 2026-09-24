"""fal Whisper local cost: ceil(inference_time) × $0.0008 × USD_TO_CNY."""

from __future__ import annotations

import math

from magicdub_cli import constants as C
from magicdub_cli.adapters.asr.fal_whisper import _cost_cny_from_inference
from magicdub_cli.errors import USD_TO_CNY


def test_whisper_cost_ceil() -> None:
    # ceil(1.608) = 2 → 2 * 0.0008 * 7 = 0.0112
    assert _cost_cny_from_inference(1.608) == round(2 * C.WHISPER_USD_PER_COMPUTE_SEC * USD_TO_CNY, 8)
    assert math.ceil(1.608) == 2


def test_whisper_cost_exact_second() -> None:
    assert _cost_cny_from_inference(3.0) == round(3 * C.WHISPER_USD_PER_COMPUTE_SEC * USD_TO_CNY, 8)


def test_whisper_cost_missing() -> None:
    assert _cost_cny_from_inference(None) is None
    assert _cost_cny_from_inference(-1.0) is None
