"""Adapter base contract: normalized I/O only; write under tmp/<step>/; never touch state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Adapter(ABC):
    """External capability behind a slot."""

    adapter_id: str
    slot: str  # sep | asr | translation | tts

    @abstractmethod
    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        """Execute and return product refs plus ``cost_cny`` (CNY float or None)."""
