"""Shared Bailian (DashScope) async file ASR helpers for magicdub-cli adapters."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    INPUT_INVALID,
    AdapterError,
    classify_http,
)
from magicdub_cli.ffmpeg_util import FFmpegError, run_ffmpeg

DEFAULT_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"
POLL_INTERVAL_S = 5.0
POLL_DEADLINE_S = 1800.0

# Same filter snapshot as magicdub-skills Fun-ASR / Qwen ASR.
SPECIAL_WORD_FILTER = json.dumps(
    {
        "filter_with_signed": {"word_list": ["肏屄"]},
        "system_reserved_filter": False,
    },
    ensure_ascii=False,
)


def language_hints(language: str | None) -> list[str]:
    if not language:
        return []
    if language == "zh-Hans":
        return ["zh"]
    return [language.split("-")[0]]


def normalize_base_url(base: str | None) -> str:
    raw = (base or "").strip().rstrip("/")
    return raw or DEFAULT_DASHSCOPE_BASE


def prepare_asr_wav(speech_path: Path, tmp_dir: Path) -> Path:
    """16 kHz mono PCM16 WAV for Bailian diarization (adapter-local; does not alter slot speech)."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / "asr_input_16k_mono.wav"
    try:
        run_ffmpeg(
            [
                "-i",
                str(speech_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(out),
            ]
        )
    except FFmpegError as exc:
        raise AdapterError(INPUT_INVALID, f"bailian asr prep failed: {exc}") from exc
    return out


def submit_transcription(
    *,
    base_url: str,
    api_key: str,
    model: str,
    file_url: str,
    parameters: dict[str, Any],
) -> str:
    base = normalize_base_url(base_url)
    url = f"{base}/services/audio/asr/transcription"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": model,
        "input": {"file_urls": [file_url]},
        "parameters": parameters,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"bailian submit network: {exc}") from exc
    if resp.status_code >= 400:
        raise AdapterError(
            classify_http(resp.status_code),
            f"bailian submit HTTP {resp.status_code}: {resp.text[:500]}",
        )
    try:
        body = resp.json()
    except ValueError as exc:
        raise AdapterError(EXTERNAL_FATAL, f"bailian submit non-json: {resp.text[:300]}") from exc
    task_id = (body.get("output") or {}).get("task_id") if isinstance(body, dict) else None
    if not isinstance(task_id, str) or not task_id.strip():
        raise AdapterError(EXTERNAL_FATAL, f"bailian submit missing task_id: {body}")
    return task_id.strip()


def poll_until_succeeded(
    *,
    base_url: str,
    api_key: str,
    task_id: str,
) -> dict[str, Any]:
    base = normalize_base_url(base_url)
    url = f"{base}/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + POLL_DEADLINE_S
    with httpx.Client(timeout=httpx.Timeout(30.0, read=60.0)) as client:
        while time.time() < deadline:
            try:
                resp = client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise AdapterError(EXTERNAL_RETRYABLE, f"bailian poll network: {exc}") from exc
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(POLL_INTERVAL_S)
                continue
            if resp.status_code >= 400:
                raise AdapterError(
                    classify_http(resp.status_code),
                    f"bailian poll HTTP {resp.status_code}: {resp.text[:500]}",
                )
            try:
                body = resp.json()
            except ValueError as exc:
                raise AdapterError(EXTERNAL_FATAL, f"bailian poll non-json: {resp.text[:300]}") from exc
            if not isinstance(body, dict):
                raise AdapterError(EXTERNAL_FATAL, f"bailian poll bad body: {body!r}")
            output = body.get("output") if isinstance(body.get("output"), dict) else {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return body
            if status in ("FAILED", "CANCELLED"):
                raise AdapterError(EXTERNAL_FATAL, f"bailian task {status}: {body}")
            if status not in ("PENDING", "RUNNING", None):
                # Unknown but keep polling briefly when still in-flight shapes appear.
                pass
            time.sleep(POLL_INTERVAL_S)
    raise AdapterError(EXTERNAL_RETRYABLE, f"bailian poll timed out task_id={task_id}")


def download_transcription(task_body: dict[str, Any], dest: Path) -> dict[str, Any]:
    output = task_body.get("output") if isinstance(task_body.get("output"), dict) else {}
    results = output.get("results")
    if not isinstance(results, list) or not results:
        raise AdapterError(EXTERNAL_FATAL, f"bailian missing results: {task_body}")
    item = results[0]
    if not isinstance(item, dict):
        raise AdapterError(EXTERNAL_FATAL, "bailian result item invalid")
    if item.get("subtask_status") != "SUCCEEDED":
        raise AdapterError(EXTERNAL_FATAL, f"bailian subtask not succeeded: {item}")
    tx_url = item.get("transcription_url")
    if not isinstance(tx_url, str) or not tx_url.startswith("https://"):
        raise AdapterError(EXTERNAL_FATAL, f"bailian bad transcription_url: {item}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as client:
            resp = client.get(tx_url)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"bailian transcript download network: {exc}") from exc
    if resp.status_code != 200:
        raise AdapterError(
            classify_http(resp.status_code),
            f"bailian transcript download HTTP {resp.status_code}",
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise AdapterError(EXTERNAL_FATAL, f"bailian transcript non-json: {resp.text[:300]}") from exc
    if not isinstance(data, dict):
        raise AdapterError(EXTERNAL_FATAL, "bailian transcript root not object")
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def parse_sentences(transcript_json: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    sentences: list[dict[str, Any]] = []
    texts: list[str] = []
    for tr in transcript_json.get("transcripts") or []:
        if not isinstance(tr, dict):
            continue
        for s in tr.get("sentences") or []:
            if not isinstance(s, dict):
                continue
            text = str(s.get("text") or "").strip()
            begin = s.get("begin_time")
            end = s.get("end_time")
            if begin is None or end is None:
                continue
            speaker = s.get("speaker_id")
            sentences.append(
                {
                    "start_ms": int(begin),
                    "end_ms": int(end),
                    "text": text,
                    "speaker_id": str(speaker) if speaker is not None else "SPEAKER_00",
                }
            )
            if text:
                texts.append(text)
    sentences.sort(key=lambda x: x["start_ms"])
    return " ".join(texts).strip(), sentences


def content_duration_seconds(transcript_json: dict[str, Any]) -> float | None:
    """Sum channel content_duration_in_milliseconds from transcription JSON."""
    total_ms = 0
    found = False
    for tr in transcript_json.get("transcripts") or []:
        if not isinstance(tr, dict):
            continue
        ms = tr.get("content_duration_in_milliseconds")
        if ms is None:
            continue
        try:
            total_ms += int(ms)
            found = True
        except (TypeError, ValueError):
            continue
    if not found:
        return None
    return total_ms / 1000.0


def usage_duration_seconds(task_body: dict[str, Any]) -> float | None:
    usage = task_body.get("usage")
    if not isinstance(usage, dict):
        return None
    dur = usage.get("duration")
    try:
        if dur is None:
            return None
        return float(dur)
    except (TypeError, ValueError):
        return None


def extract_token_usage(task_body: dict[str, Any]) -> tuple[int | None, int | None]:
    """Best-effort input/output token counts from task envelope (field names vary)."""
    usage = task_body.get("usage")
    if not isinstance(usage, dict):
        return None, None

    def _pick(*names: str) -> int | None:
        for name in names:
            if name not in usage:
                continue
            try:
                return int(usage[name])
            except (TypeError, ValueError):
                continue
        return None

    inp = _pick(
        "input_tokens",
        "prompt_tokens",
        "input_token_count",
        "prompt_token_count",
    )
    out = _pick(
        "output_tokens",
        "completion_tokens",
        "output_token_count",
        "completion_token_count",
    )
    # Nested models sometimes nest under input_tokens / output_tokens objects.
    if inp is None and isinstance(usage.get("input_tokens"), dict):
        nested = usage["input_tokens"]
        for k in ("total", "text", "audio", "count"):
            if k in nested:
                try:
                    inp = int(nested[k])
                    break
                except (TypeError, ValueError):
                    pass
    if out is None and isinstance(usage.get("output_tokens"), dict):
        nested = usage["output_tokens"]
        for k in ("total", "text", "count"):
            if k in nested:
                try:
                    out = int(nested[k])
                    break
                except (TypeError, ValueError):
                    pass
    return inp, out
