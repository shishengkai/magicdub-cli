"""fal/whisper ASR with diarize."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import USD_TO_CNY
from magicdub_cli.fal_api import run_model, upload_file


class WhisperAdapter(Adapter):
    adapter_id = "fal/whisper"
    endpoint = "fal-ai/whisper"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        speech_path = Path(inputs["speech_path"])
        language = inputs.get("language")  # e.g. en — whisper accepts null for auto
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Upload as-is; fal Whisper accepts mp3/mp4/mpeg/mpga/m4a/wav/webm (no local transcode).
        url = upload_file(speech_path, api_key)
        lang_param = None
        if language:
            # fal whisper uses short codes like "en"
            lang_param = language.split("-")[0]
        result, _fal_cost, inference_time, _downloaded = run_model(
            endpoint=self.endpoint,
            payload={
                "audio_url": url,
                "task": "transcribe",
                "language": lang_param,
                "chunk_level": "segment",
                "diarize": True,
                "batch_size": 64,
                "prompt": "",
                "num_speakers": None,
            },
            api_key=api_key,
        )
        # Local estimate: ignore fal_api billing/pricing; use status inference_time.
        cost_cny = _cost_cny_from_inference(inference_time)

        chunks = result.get("chunks") or result.get("segments") or []
        sentences: list[dict[str, Any]] = []
        texts: list[str] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            ts = chunk.get("timestamp") or chunk.get("timestamps") or [None, None]
            if isinstance(ts, dict):
                start, end = ts.get("start"), ts.get("end")
            else:
                start = ts[0] if len(ts) > 0 else None
                end = ts[1] if len(ts) > 1 else None
            if start is None or end is None:
                continue
            text = (chunk.get("text") or "").strip()
            speaker = chunk.get("speaker") or chunk.get("speaker_id") or "SPEAKER_00"
            start_ms = int(round(float(start) * 1000))
            end_ms = int(round(float(end) * 1000))
            sentences.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                    "speaker_id": str(speaker),
                }
            )
            if text:
                texts.append(text)

        sentences.sort(key=lambda s: s["start_ms"])
        transcript = (result.get("text") or " ".join(texts)).strip()
        return {
            "transcript": transcript,
            "sentences": sentences,
            "cost_cny": cost_cny,
        }


def _cost_cny_from_inference(inference_time: float | None) -> float | None:
    """ceil(compute_s) × $0.0008 × USD_TO_CNY; None if duration unknown."""
    if inference_time is None or inference_time < 0:
        return None
    billable = math.ceil(inference_time)
    return round(billable * C.WHISPER_USD_PER_COMPUTE_SEC * USD_TO_CNY, 8)
