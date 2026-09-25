"""OpenRouter Fish Instant clone helpers (PCM speech API → WAV)."""

from __future__ import annotations

import base64
import io
import wave
from email.message import Message
from pathlib import Path

import httpx

from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    INPUT_INVALID,
    AdapterError,
    classify_http,
)

SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
# Exact OpenRouter model ids — free suffix required for the free tier.
KNOWN_MODELS = frozenset(
    {
        "fish-audio/s2.1-pro-free:free",
        "fish-audio/s2.1-pro",
    }
)
MAX_REFERENCE_BYTES = 15 * 1024 * 1024

# App attribution (https://openrouter.ai/docs/app-attribution).
# HTTP-Referer is required for public rankings; Title alone does not create an app page.
OPENROUTER_APP_TITLE = "MagicDub"
# Product / homepage URL — required for public rankings (not localhost).
OPENROUTER_HTTP_REFERER = "https://magicdub.com"
# Optional marketplace categories (comma-separated, recognized slugs only).
OPENROUTER_APP_CATEGORIES = "audio-gen,video-gen"


def attribution_headers() -> dict[str, str]:
    """Headers for OpenRouter public app rankings / analytics."""
    headers: dict[str, str] = {
        "X-OpenRouter-Title": OPENROUTER_APP_TITLE,
        # Back-compat alias still documented by OpenRouter.
        "X-Title": OPENROUTER_APP_TITLE,
    }
    referer = (OPENROUTER_HTTP_REFERER or "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    categories = (OPENROUTER_APP_CATEGORIES or "").strip()
    if categories:
        headers["X-OpenRouter-Categories"] = categories
    return headers


def pcm_to_wav(data: bytes, content_type: str) -> bytes:
    """Wrap provider PCM16LE using Content-Type rate/channels metadata; no resample."""
    message = Message()
    message["Content-Type"] = content_type
    try:
        rate = int(message.get_param("rate"))
        channels = int(message.get_param("channels"))
        if (
            message.get_content_type() != "audio/pcm"
            or not 8000 <= rate <= 192000
            or channels not in (1, 2)
            or not data
            or len(data) % (channels * 2)
        ):
            raise ValueError("invalid PCM or metadata")
    except (TypeError, ValueError) as exc:
        raise AdapterError(
            EXTERNAL_FATAL, "openrouter PCM missing valid rate/channels metadata"
        ) from exc
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setparams(
            (channels, 2, rate, len(data) // (channels * 2), "NONE", "not compressed")
        )
        audio.writeframes(data)
    return stream.getvalue()


def instant_clone(
    *,
    api_key: str,
    model: str,
    text: str,
    source_text: str,
    reference_path: Path,
    dest: Path,
) -> Path:
    """POST Instant clone; write WAV (PCM samples unchanged) to ``dest``."""
    if model not in KNOWN_MODELS:
        raise AdapterError(INPUT_INVALID, f"unknown openrouter model: {model}")
    if not text.strip():
        raise AdapterError(INPUT_INVALID, "openrouter tts text empty")
    if not source_text.strip():
        raise AdapterError(
            INPUT_INVALID,
            "openrouter Instant clone requires source_text (reference transcript)",
        )
    if not reference_path.is_file():
        raise AdapterError(INPUT_INVALID, "openrouter reference audio missing")
    size = reference_path.stat().st_size
    if not 0 < size <= MAX_REFERENCE_BYTES:
        raise AdapterError(
            INPUT_INVALID,
            "openrouter reference must be non-empty and ≤ 15 MiB",
        )

    encoded = base64.b64encode(reference_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "input": text,
        "response_format": "pcm",
        "speed": 1,
        "input_references": [
            {
                "type": "input_audio",
                "input_audio": {"data": "data:audio/wav;base64," + encoded},
            },
            {"type": "text", "text": source_text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        **attribution_headers(),
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, read=300.0)) as client:
            resp = client.post(SPEECH_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"openrouter network: {exc}") from exc

    if resp.status_code != 200:
        raise AdapterError(
            classify_http(resp.status_code),
            f"openrouter HTTP {resp.status_code}",
        )

    content_type = resp.headers.get("Content-Type") or ""
    wav = pcm_to_wav(resp.content, content_type)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".download")
    tmp.write_bytes(wav)
    tmp.replace(dest)
    return dest
