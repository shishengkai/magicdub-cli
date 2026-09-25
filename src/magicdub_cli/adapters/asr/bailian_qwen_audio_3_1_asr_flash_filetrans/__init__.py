"""bailian/qwen-audio-3.1-asr-flash-filetrans — DashScope Qwen Audio 3.1 via fal CDN."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.bailian_asr import (
    SPECIAL_WORD_FILTER,
    download_transcription,
    extract_token_usage,
    language_hints,
    parse_sentences,
    poll_until_succeeded,
    prepare_asr_wav,
    submit_transcription,
)
from magicdub_cli.errors import INPUT_INVALID, AdapterError
from magicdub_cli.fal_api import upload_file


class QwenAudio31AsrFlashFiletransAdapter(Adapter):
    adapter_id = "bailian/qwen-audio-3.1-asr-flash-filetrans"
    slot = "asr"
    model = "qwen-audio-3.1-asr-flash-filetrans"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        fal_key = inputs["fal_key"]
        base_url = inputs.get("base_url")
        speech_path = Path(inputs["speech_path"])
        language = inputs.get("language")
        if not speech_path.is_file():
            raise AdapterError(INPUT_INVALID, "asr speech missing")

        tmp_dir.mkdir(parents=True, exist_ok=True)
        asr_wav = prepare_asr_wav(speech_path, tmp_dir)
        audio_url = upload_file(asr_wav, fal_key)
        params: dict[str, Any] = {
            "diarization_enabled": True,
            "special_word_filter": SPECIAL_WORD_FILTER,
        }
        hints = language_hints(language if isinstance(language, str) else None)
        if hints:
            params["language_hints"] = hints

        task_id = submit_transcription(
            base_url=base_url,
            api_key=api_key,
            model=self.model,
            file_url=audio_url,
            parameters=params,
        )
        task_body = poll_until_succeeded(base_url=base_url, api_key=api_key, task_id=task_id)
        # Persist raw task envelope for token-field verification / debugging.
        (tmp_dir / "task.json").write_text(
            json.dumps(task_body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        transcript_json = download_transcription(task_body, tmp_dir / "transcription.json")
        transcript, sentences = parse_sentences(transcript_json)
        cost_cny = _cost_cny_tokens(task_body)
        return {
            "transcript": transcript,
            "sentences": sentences,
            "cost_cny": cost_cny,
            "usage": task_body.get("usage"),
        }


def _cost_cny_tokens(task_body: dict[str, Any]) -> float | None:
    """Beijing Qwen 3.1 filetrans: input/output tokens × ¥/MTok; null if usage missing."""
    inp, out = extract_token_usage(task_body)
    if inp is None and out is None:
        return None
    inp_n = float(inp or 0)
    out_n = float(out or 0)
    cost = (inp_n / 1_000_000.0) * C.QWEN31_ASR_INPUT_CNY_PER_MTOK + (
        out_n / 1_000_000.0
    ) * C.QWEN31_ASR_OUTPUT_CNY_PER_MTOK
    return round(cost, 8)
