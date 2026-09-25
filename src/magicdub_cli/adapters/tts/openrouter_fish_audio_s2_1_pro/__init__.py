"""openrouter/fish-audio/s2.1-pro — OpenRouter Fish Instant clone (paid)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import USD_TO_CNY
from magicdub_cli.openrouter_tts import instant_clone


class OpenRouterFishS21ProAdapter(Adapter):
    adapter_id = "openrouter/fish-audio/s2.1-pro"
    slot = "tts"
    model = "fish-audio/s2.1-pro"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        text = str(inputs["text"])
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out = instant_clone(
            api_key=inputs["api_key"],
            model=self.model,
            text=text,
            source_text=str(inputs.get("source_text") or ""),
            reference_path=Path(inputs["reference_path"]),
            dest=tmp_dir / "tts.wav",
        )
        return {"audio_path": out, "cost_cny": _cost_cny_from_text(text)}


def _cost_cny_from_text(text: str) -> float:
    """OpenRouter list snapshot: $0.000015／UTF-8 byte of target text × USD_TO_CNY."""
    nbytes = len(text.encode("utf-8"))
    return round(nbytes * C.FISH_S21_PRO_USD_PER_UTF8_BYTE * USD_TO_CNY, 8)
