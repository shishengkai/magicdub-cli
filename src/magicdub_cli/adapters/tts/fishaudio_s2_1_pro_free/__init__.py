"""fishaudio/s2.1-pro-free — Fish Instant clone (free development endpoint)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli.adapters.base import Adapter
from magicdub_cli.fish_tts import instant_clone


class FishS21ProFreeAdapter(Adapter):
    adapter_id = "fishaudio/s2.1-pro-free"
    model = "s2.1-pro-free"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out = instant_clone(
            api_key=inputs["api_key"],
            model=self.model,
            text=str(inputs["text"]),
            source_text=str(inputs.get("source_text") or ""),
            reference_path=Path(inputs["reference_path"]),
            dest=tmp_dir / "tts.wav",
        )
        return {"audio_path": out, "cost_cny": 0.0}
