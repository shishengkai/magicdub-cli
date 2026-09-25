"""deepseek/deepseek-flash — single translate() entry with history."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    AdapterError,
    classify_http,
)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
_SHANGHAI = ZoneInfo("Asia/Shanghai")

# deepseek-flash CNY / 1M tokens — https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
# Peak: Beijing Mon–Fri 09:00–12:00 & 14:00–18:00 (excl. statutory holidays; see _is_peak).
# Idle = half of peak. Response has no money field; bill from usage tokens.
_CNY_PER_M_PEAK = {
    "cache_hit": 0.04,
    "cache_miss": 2.0,
    "output": 8.0,
}

_SYSTEM_BASE = (
    "You are a professional audiovisual translator for dubbing. "
    "Translate faithfully into natural spoken language. "
    "Return ONLY valid JSON: {\"translations\":[{\"id\":<int>,\"text\":\"...\"},...]} "
    "with the same ids as the task. No markdown."
)

_SYSTEM_REVISION = (
    " This is a LENGTH REVISION pass for dubbing timing. "
    "Each sentence has target_duration_ms and prior TTS measurements. "
    "Rewrite so the NEXT TTS take is closer to target_duration_ms. "
    "If fitting_ratio > 1 (or action says TOO LONG): shorten — "
    "fewer syllables, tighter wording. "
    "If fitting_ratio < 1 (or action says TOO SHORT): lengthen slightly "
    "with natural speech, not filler. "
    "Do not change meaning, speaker intent, or facts. "
    "Prefer spoken cadence over any character-count formula; "
    "never assume a fixed chars-per-second rate."
)


def build_messages(
    *,
    transcript: str,
    src_language: str,
    tgt_language: str,
    sentences: list[dict[str, Any]],
    max_attempt: int | None = None,
) -> list[dict[str, str]]:
    """Build chat messages for initial or revision translate (history empty vs non-empty)."""
    is_revision = any(item.get("history") for item in sentences)
    system = _SYSTEM_BASE + (_SYSTEM_REVISION if is_revision else "")
    context = (
        f"Full source transcript (context only — do NOT translate the whole block):\n"
        f"Language: {src_language}\n---\n{transcript}\n---"
    )
    lines: list[str] = [f"Target language: {tgt_language}"]
    if is_revision:
        attempt = next((int(item.get("attempt") or 0) for item in sentences), 0)
        cap = f" of max {max_attempt}" if max_attempt else ""
        lines.append(f"Pass: revise_timing (attempt={attempt}{cap})")
        lines.append(
            "Only revise the sentences below. Use prior TTS duration vs target_duration_ms. "
            "Goal: next TTS duration ≈ target_duration_ms."
        )
    else:
        lines.append("Pass: initial")
        lines.append(
            "Translate each sentence. Aim for spoken length that can fit about "
            "target_duration_ms when read naturally (rough guide only; no prior TTS yet)."
        )

    for item in sentences:
        part = [
            f"- id={item['id']}",
            f"  source: {item['src_text']}",
            f"  target_duration_ms: {item['target_duration_ms']}",
        ]
        history = item.get("history") or []
        if history:
            part.append("  prior attempts:")
            for h in history:
                ratio = h.get("fitting_ratio")
                if ratio is not None and float(ratio) > 1:
                    action = "TOO LONG — shorten; keep meaning"
                elif ratio is not None and float(ratio) < 1:
                    action = "TOO SHORT — lengthen; keep meaning"
                else:
                    action = "revise length toward target; keep meaning"
                part.append(
                    f"    - attempt={h.get('attempt')}"
                    f" text={h.get('text')!r}"
                    f" tts_duration_ms={h.get('tts_duration_ms')}"
                    f" fitting_ratio={ratio}"
                    f" action: {action}"
                )
        lines.extend(part)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": context},
        {"role": "user", "content": "\n".join(lines)},
    ]


class DeepSeekFlashAdapter(Adapter):
    adapter_id = "deepseek/deepseek-flash"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        transcript = inputs["transcript"]
        src_language = inputs["src_language"]
        tgt_language = inputs["tgt_language"]
        sentences = inputs["sentences"]
        max_attempt = inputs.get("max_attempt")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        messages = build_messages(
            transcript=transcript,
            src_language=src_language,
            tgt_language=tgt_language,
            sentences=sentences,
            max_attempt=int(max_attempt) if max_attempt is not None else None,
        )

        payload = {
            "model": "deepseek-flash",
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
        }

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        DEEPSEEK_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if resp.status_code >= 400:
                    raise AdapterError(
                        classify_http(resp.status_code),
                        f"deepseek HTTP {resp.status_code}: {resp.text[:500]}",
                    )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                translations = _parse_translations(content)
                usage = data.get("usage") or {}
                cost = _cost_from_usage(usage)
                return {"translations": translations, "cost_cny": cost, "raw": content}
            except AdapterError as exc:
                last_err = exc
                if exc.code != EXTERNAL_RETRYABLE or attempt == 2:
                    raise
            except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
                last_err = AdapterError(EXTERNAL_FATAL, f"bad deepseek response: {exc}")
                if attempt == 2:
                    raise last_err from exc
        assert last_err is not None
        raise last_err


def _parse_translations(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    items = data.get("translations") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("translations not a list")
    out = []
    for item in items:
        out.append({"id": int(item["id"]), "text": str(item["text"]).strip()})
    return out


def _is_peak(*, now: datetime | None = None) -> bool:
    """Peak window in Asia/Shanghai; weekends are idle.

    Statutory holidays are all-day idle on DeepSeek's page; this helper does
    not load a holiday calendar, so holiday weekday peak hours may overestimate.
    """
    dt = now.astimezone(_SHANGHAI) if now is not None else datetime.now(_SHANGHAI)
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    return (9 * 60 <= minutes < 12 * 60) or (14 * 60 <= minutes < 18 * 60)


def _rates_cny_per_m(*, now: datetime | None = None) -> dict[str, float]:
    peak = _is_peak(now=now)
    scale = 1.0 if peak else 0.5
    return {k: v * scale for k, v in _CNY_PER_M_PEAK.items()}


def _cost_from_usage(
    usage: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float | None:
    """Estimate CNY from usage; API does not return a spend field.

    Uses ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens`` when present;
    otherwise treats all ``prompt_tokens`` as cache miss. ``completion_tokens``
    (including reasoning) billed as output.
    """
    cout = usage.get("completion_tokens")
    if cout is None:
        return None
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    if hit is None or miss is None:
        pin = usage.get("prompt_tokens")
        if pin is None:
            return None
        hit_i, miss_i = 0, int(pin)
    else:
        hit_i, miss_i = int(hit), int(miss)
    rates = _rates_cny_per_m(now=now)
    cny = (
        (hit_i / 1_000_000) * rates["cache_hit"]
        + (miss_i / 1_000_000) * rates["cache_miss"]
        + (int(cout) / 1_000_000) * rates["output"]
    )
    return round(cny, 8)
