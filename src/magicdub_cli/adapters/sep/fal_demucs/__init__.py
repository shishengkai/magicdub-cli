"""fal/demucs — vocals + background (original − vocals)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import INPUT_INVALID, USD_TO_CNY, AdapterError
from magicdub_cli.fal_api import run_model, upload_file
from magicdub_cli.ffmpeg_util import FFmpegError, audio_duration_s, run_ffmpeg


class DemucsAdapter(Adapter):
    adapter_id = "fal/demucs"
    endpoint = "fal-ai/demucs"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        audio_path = Path(inputs["audio_path"])
        if not audio_path.is_file():
            raise AdapterError(INPUT_INVALID, "sep input audio missing")

        tmp_dir.mkdir(parents=True, exist_ok=True)
        vocals_path = tmp_dir / "vocals.wav"
        url = upload_file(audio_path, api_key)
        result, _fal_cost, _inference_time = run_model(
            endpoint=self.endpoint,
            payload={
                "audio_url": url,
                "model": "htdemucs_ft",
                "stems": ["vocals"],
                "shifts": 1,
                "overlap": 0.25,
                "output_format": "wav",
            },
            api_key=api_key,
            download_to=vocals_path,
            result_key="vocals",
        )
        if not vocals_path.is_file():
            # response may nest differently
            vocals_obj = result.get("vocals") if isinstance(result, dict) else None
            if not (isinstance(vocals_obj, dict) and vocals_obj.get("url")):
                raise AdapterError("external_fatal", f"demucs missing vocals: {result}")

        # Billing is audio seconds (Pricing $0.0007); ignore fal_api estimate.
        try:
            dur_s = audio_duration_s(audio_path)
        except FFmpegError as exc:
            raise AdapterError(INPUT_INVALID, f"cannot measure sep input duration: {exc}") from exc
        cost_cny = _cost_cny_from_audio_duration(dur_s)

        speech = tmp_dir / "speech.wav"
        non_speech = tmp_dir / "non_speech.wav"
        # Keep vocals as speech (re-encode float32 for consistency)
        try:
            run_ffmpeg(["-i", str(vocals_path), "-c:a", "pcm_f32le", str(speech)])
            # background = original + (-1 * vocals), duration matched
            filter_complex = (
                f"[0:a]aresample=async=1,aformat=sample_fmts=fltp,apad,atrim=duration={dur_s:.6f}[o];"
                f"[1:a]aresample=async=1,aformat=sample_fmts=fltp,volume=-1.0,"
                f"apad,atrim=duration={dur_s:.6f}[v];"
                f"[o][v]amix=inputs=2:normalize=0:duration=first[out]"
            )
            run_ffmpeg(
                [
                    "-i",
                    str(audio_path),
                    "-i",
                    str(speech),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[out]",
                    "-c:a",
                    "pcm_f32le",
                    str(non_speech),
                ]
            )
        except FFmpegError as exc:
            raise AdapterError(INPUT_INVALID, str(exc), cost_cny=cost_cny) from exc

        return {
            "speech_path": speech,
            "non_speech_path": non_speech,
            "cost_cny": cost_cny,
        }


def _cost_cny_from_audio_duration(dur_s: float) -> float:
    """ceil(audio_s) × $0.0007 × USD_TO_CNY."""
    billable = math.ceil(dur_s)
    return round(billable * C.DEMUCS_USD_PER_AUDIO_SEC * USD_TO_CNY, 8)
