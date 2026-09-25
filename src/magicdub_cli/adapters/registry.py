"""adapter_id → implementation registry."""

from __future__ import annotations

from magicdub_cli.adapters.base import Adapter


def _load() -> dict[str, type[Adapter]]:
    from magicdub_cli.adapters.asr.bailian_fun_asr import FunAsrAdapter
    from magicdub_cli.adapters.asr.bailian_qwen_audio_3_1_asr_flash_filetrans import (
        QwenAudio31AsrFlashFiletransAdapter,
    )
    from magicdub_cli.adapters.asr.fal_whisper import WhisperAdapter
    from magicdub_cli.adapters.sep.fal_demucs import DemucsAdapter
    from magicdub_cli.adapters.sep.fal_sam_audio import SamAudioAdapter
    from magicdub_cli.adapters.sep.mvsep_dnr_v3 import MvsepDnrV3Adapter
    from magicdub_cli.adapters.translation.deepseek_deepseek_flash import DeepSeekFlashAdapter
    from magicdub_cli.adapters.tts.fal_index_tts_2 import IndexTTS2Adapter
    from magicdub_cli.adapters.tts.fishaudio_s2_1_pro import FishS21ProAdapter
    from magicdub_cli.adapters.tts.fishaudio_s2_1_pro_free import FishS21ProFreeAdapter
    from magicdub_cli.adapters.tts.openrouter_fish_audio_s2_1_pro import (
        OpenRouterFishS21ProAdapter,
    )
    from magicdub_cli.adapters.tts.openrouter_fish_audio_s2_1_pro_free import (
        OpenRouterFishS21ProFreeAdapter,
    )

    adapters: list[type[Adapter]] = [
        DemucsAdapter,
        SamAudioAdapter,
        MvsepDnrV3Adapter,
        WhisperAdapter,
        FunAsrAdapter,
        QwenAudio31AsrFlashFiletransAdapter,
        DeepSeekFlashAdapter,
        IndexTTS2Adapter,
        FishS21ProFreeAdapter,
        FishS21ProAdapter,
        OpenRouterFishS21ProFreeAdapter,
        OpenRouterFishS21ProAdapter,
    ]
    return {cls.adapter_id: cls for cls in adapters}


_REGISTRY: dict[str, type[Adapter]] | None = None


def _registry() -> dict[str, type[Adapter]]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    return _REGISTRY


def get_adapter(adapter_id: str) -> Adapter:
    cls = _registry().get(adapter_id)
    if cls is None:
        raise KeyError(f"unknown adapter_id: {adapter_id}")
    return cls()


def known_adapter_ids() -> list[str]:
    return sorted(_registry())


def adapter_ids_for_slot(slot: str) -> list[str]:
    """Registered adapter_ids for a pipeline slot, sorted."""
    return sorted(aid for aid, cls in _registry().items() if cls.slot == slot)
