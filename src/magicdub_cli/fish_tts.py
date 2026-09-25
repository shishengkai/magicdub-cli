"""Fish Audio Instant clone helpers (msgpack TTS + WAV size repair)."""

from __future__ import annotations

import io
import struct
import wave
from pathlib import Path
from typing import Any

import httpx
import msgpack

from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    INPUT_INVALID,
    AdapterError,
    classify_http,
)

TTS_URL = "https://api.fish.audio/v1/tts"
# Exact model header values — unknown names silently fall back to paid s2.1-pro on Fish side.
KNOWN_MODELS = frozenset({"s2.1-pro-free", "s2.1-pro"})

# Snapshot aligned with magicdub-skills fish Instant clone.
DEFAULT_PARAMS: dict[str, Any] = {
    "format": "wav",
    "sample_rate": 44100,
    "latency": "normal",
    "temperature": 0.7,
    "top_p": 0.7,
    "prosody": {"speed": 1, "volume": 0, "normalize_loudness": True},
}


def normalize_wav(data: bytes) -> bytes:
    """Repair only Fish's observed streaming size markers; never alter PCM samples."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AdapterError(EXTERNAL_FATAL, "fish response is not a valid WAV")
    repaired = data
    if (
        data[12:20] == b"fmt \x10\x00\x00\x00"
        and data[36:40] == b"data"
        and struct.unpack_from("<I", data, 4)[0] == 0xFFFFFF24
        and struct.unpack_from("<I", data, 40)[0] == 0xFFFFFF00
    ):
        repaired = (
            data[:4]
            + struct.pack("<I", len(data) - 8)
            + data[8:40]
            + struct.pack("<I", len(data) - 44)
            + data[44:]
        )
    try:
        if struct.unpack_from("<I", repaired, 4)[0] != len(repaired) - 8:
            raise ValueError("incomplete RIFF")
        with wave.open(io.BytesIO(repaired), "rb") as audio:
            frames = audio.getnframes()
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 44100
                or frames <= 0
                or len(audio.readframes(frames)) != frames * 2
            ):
                raise ValueError("invalid PCM")
        if repaired is not data and (len(repaired) - 44) % 2:
            raise ValueError("partial PCM frame")
    except (ValueError, EOFError, wave.Error, struct.error) as exc:
        raise AdapterError(EXTERNAL_FATAL, "fish WAV incomplete or unexpected format") from exc
    return repaired


def instant_clone(
    *,
    api_key: str,
    model: str,
    text: str,
    source_text: str,
    reference_path: Path,
    dest: Path,
) -> Path:
    """POST Instant clone; write normalized mono 44.1 kHz PCM16 WAV to ``dest``."""
    if model not in KNOWN_MODELS:
        raise AdapterError(INPUT_INVALID, f"unknown fish model header: {model}")
    if not text.strip():
        raise AdapterError(INPUT_INVALID, "fish tts text empty")
    if not source_text.strip():
        raise AdapterError(
            INPUT_INVALID,
            "fish Instant clone requires source_text (reference transcript)",
        )
    if not reference_path.is_file():
        raise AdapterError(INPUT_INVALID, "fish reference audio missing")

    payload = {
        **DEFAULT_PARAMS,
        "text": text,
        "references": [
            {"audio": reference_path.read_bytes(), "text": source_text},
        ],
    }
    packed = msgpack.packb(payload, use_bin_type=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/msgpack",
        "model": model,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, read=300.0)) as client:
            resp = client.post(TTS_URL, content=packed, headers=headers)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"fish network: {exc}") from exc

    if resp.status_code != 200:
        code = classify_http(resp.status_code)
        # 4xx auth/quota often retryable after user fix; keep message short (no body echo).
        raise AdapterError(code, f"fish HTTP {resp.status_code}")

    wav = normalize_wav(resp.content)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".download")
    tmp.write_bytes(wav)
    tmp.replace(dest)
    return dest
