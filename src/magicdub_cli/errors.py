"""Shared error codes and step result helpers."""

from __future__ import annotations

from dataclasses import dataclass

EXTERNAL_RETRYABLE = "external_retryable"
EXTERNAL_FALLBACK = "external_fallback"
EXTERNAL_FATAL = "external_fatal"
INPUT_INVALID = "input_invalid"
ADAPTER_EXHAUSTED = "adapter_exhausted"


@dataclass
class StepResult:
    ok: bool
    error_code: str | None = None
    message: str | None = None
    adapter_id: str | None = None


def ok_result(adapter_id: str | None = None) -> StepResult:
    return StepResult(ok=True, adapter_id=adapter_id)


def fail_result(code: str, message: str, adapter_id: str | None = None) -> StepResult:
    return StepResult(ok=False, error_code=code, message=message, adapter_id=adapter_id)


class AdapterError(Exception):
    def __init__(self, code: str, message: str, *, cost_cny: float | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.cost_cny = cost_cny


def classify_http(status: int) -> str:
    if status in (429, 500, 502, 503, 504):
        return EXTERNAL_RETRYABLE
    if status == 402:
        return EXTERNAL_FALLBACK
    if status in (401, 403):
        return EXTERNAL_FATAL
    if status >= 500:
        return EXTERNAL_RETRYABLE
    if status >= 400:
        return EXTERNAL_FATAL
    return EXTERNAL_RETRYABLE


USD_TO_CNY = 7.0
