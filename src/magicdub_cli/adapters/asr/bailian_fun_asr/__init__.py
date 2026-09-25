"""bailian/fun-asr — DashScope Fun-ASR via fal CDN HTTPS URL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.bailian_asr import (
    SPECIAL_WORD_FILTER,
    content_duration_seconds,
    download_transcription,
    language_hints,
    parse_sentences,
    poll_until_succeeded,
    prepare_asr_wav,
    submit_transcription,
    usage_duration_seconds,
)
from magicdub_cli.errors import INPUT_INVALID, AdapterError
from magicdub_cli.fal_api import upload_file


class FunAsrAdapter(Adapter):
    adapter_id = "bailian/fun-asr"
    slot = "asr"
    model = "fun-asr"

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
        transcript_json = download_transcription(task_body, tmp_dir / "transcription.json")
        transcript, sentences = parse_sentences(transcript_json)
        cost_cny = _cost_cny_duration(transcript_json, task_body)
        return {
            "transcript": transcript,
            "sentences": sentences,
            "cost_cny": cost_cny,
        }


def _cost_cny_duration(transcript_json: dict[str, Any], task_body: dict[str, Any]) -> float | None:
    """Beijing Fun-ASR: content_duration seconds × ¥0.00022; fallback usage.duration."""
    seconds = content_duration_seconds(transcript_json)
    if seconds is None:
        seconds = usage_duration_seconds(task_body)
    if seconds is None or seconds < 0:
        return None
    return round(float(seconds) * C.FUN_ASR_CNY_PER_SEC, 8)
