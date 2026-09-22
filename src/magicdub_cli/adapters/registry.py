"""adapter_id → implementation registry."""

from __future__ import annotations

from magicdub_cli.adapters.base import Adapter


def _load() -> dict[str, type[Adapter]]:
    from magicdub_cli.adapters.asr.fal_whisper import WhisperAdapter
    from magicdub_cli.adapters.sep.fal_demucs import DemucsAdapter
    from magicdub_cli.adapters.translation.deepseek_deepseek_flash import DeepSeekFlashAdapter
    from magicdub_cli.adapters.tts.fal_index_tts_2 import IndexTTS2Adapter

    adapters: list[type[Adapter]] = [
        DemucsAdapter,
        WhisperAdapter,
        DeepSeekFlashAdapter,
        IndexTTS2Adapter,
    ]
    return {cls.adapter_id: cls for cls in adapters}


_REGISTRY: dict[str, type[Adapter]] | None = None


def get_adapter(adapter_id: str) -> Adapter:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    cls = _REGISTRY.get(adapter_id)
    if cls is None:
        raise KeyError(f"unknown adapter_id: {adapter_id}")
    return cls()


def known_adapter_ids() -> list[str]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    return sorted(_REGISTRY)
