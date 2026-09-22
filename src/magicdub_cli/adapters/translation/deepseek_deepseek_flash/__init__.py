"""deepseek/deepseek-flash — single translate() entry with history."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    USD_TO_CNY,
    AdapterError,
    classify_http,
)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
# Approximate Flash rates USD / 1M tokens (input/output); refine via usage if priced later.
USD_PER_M_INPUT = 0.14
USD_PER_M_OUTPUT = 0.28


class DeepSeekFlashAdapter(Adapter):
    adapter_id = "deepseek/deepseek-flash"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        transcript = inputs["transcript"]
        src_language = inputs["src_language"]
        tgt_language = inputs["tgt_language"]
        sentences = inputs["sentences"]
        tmp_dir.mkdir(parents=True, exist_ok=True)

        system = (
            "You are a professional audiovisual translator. "
            "Translate faithfully into natural spoken language for dubbing. "
            "Return ONLY valid JSON: {\"translations\":[{\"id\":<int>,\"text\":\"...\"},...]} "
            "with the same ids as the task. No markdown."
        )
        context = (
            f"Full source transcript (context only — do NOT translate the whole block):\n"
            f"Language: {src_language}\n---\n{transcript}\n---"
        )
        lines: list[str] = [
            f"Target language: {tgt_language}",
            "Translate each sentence below. Keep meaning; make speech natural.",
        ]
        for item in sentences:
            part = [
                f"- id={item['id']}",
                f"  source: {item['src_text']}",
                f"  target_duration_ms: {item['target_duration_ms']}",
            ]
            history = item.get("history") or []
            if history:
                part.append("  prior attempts (revise length; meaning unchanged):")
                for h in history:
                    ratio = h.get("fitting_ratio")
                    hint = ""
                    if ratio is not None:
                        if ratio > 1:
                            hint = " (too long — shorten)"
                        elif ratio < 1:
                            hint = " (too short — lengthen)"
                    part.append(
                        f"    attempt={h.get('attempt')} text={h.get('text')!r} "
                        f"tts_duration_ms={h.get('tts_duration_ms')} "
                        f"fitting_ratio={ratio}{hint}"
                    )
            lines.extend(part)
        user = "\n".join(lines)

        payload = {
            "model": "deepseek-flash",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
                {"role": "user", "content": user},
            ],
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


def _cost_from_usage(usage: dict[str, Any]) -> float | None:
    pin = usage.get("prompt_tokens")
    cout = usage.get("completion_tokens")
    if pin is None or cout is None:
        return None
    usd = (int(pin) / 1_000_000) * USD_PER_M_INPUT + (int(cout) / 1_000_000) * USD_PER_M_OUTPUT
    return round(usd * USD_TO_CNY, 8)
