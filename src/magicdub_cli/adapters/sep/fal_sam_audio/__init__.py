"""fal/sam-audio — SAM Audio separate: target→speech, residual→non_speech."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import httpx

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    INPUT_INVALID,
    USD_TO_CNY,
    AdapterError,
    classify_http,
)
from magicdub_cli.fal_api import run_model, suffix_from_remote, upload_file
from magicdub_cli.ffmpeg_util import FFmpegError, audio_duration_s


class SamAudioAdapter(Adapter):
    adapter_id = "fal/sam-audio"
    endpoint = "fal-ai/sam-audio/separate"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        audio_path = Path(inputs["audio_path"])
        if not audio_path.is_file():
            raise AdapterError(INPUT_INVALID, "sep input audio missing")

        tmp_dir.mkdir(parents=True, exist_ok=True)
        speech = tmp_dir / "speech"
        url = upload_file(audio_path, api_key)
        # Params aligned with magicdub-skills `sam`, except prompt=speaking (user).
        result, _fal_cost, _inference_time, downloaded = run_model(
            endpoint=self.endpoint,
            payload={
                "audio_url": url,
                "prompt": "speaking",
                "predict_spans": False,
                "reranking_candidates": C.SAM_AUDIO_RERANKING_CANDIDATES,
                "acceleration": "balanced",
                "max_chunk_duration": 60,
                "chunk_overlap": 5,
                "output_format": "wav",  # highest quality among fal options
            },
            api_key=api_key,
            download_to=speech,
            result_key="target",
        )
        if downloaded is not None:
            speech = downloaded
        if not speech.is_file():
            target_obj = result.get("target") if isinstance(result, dict) else None
            if not (isinstance(target_obj, dict) and target_obj.get("url")):
                raise AdapterError(EXTERNAL_FATAL, f"sam-audio missing target: {result}")

        residual_obj = result.get("residual") if isinstance(result, dict) else None
        if not (isinstance(residual_obj, dict) and residual_obj.get("url")):
            raise AdapterError(EXTERNAL_FATAL, f"sam-audio missing residual: {result}")
        residual_url = str(residual_obj["url"])
        non_speech = tmp_dir / f"non_speech{suffix_from_remote(url=residual_url, file_obj=residual_obj)}"
        _download_url(residual_url, non_speech)

        bill_dur_s: float | None = None
        if isinstance(result, dict) and result.get("duration") is not None:
            try:
                out_dur = float(result["duration"])
                if out_dur > 0:
                    bill_dur_s = out_dur
            except (TypeError, ValueError):
                pass
        if bill_dur_s is None:
            try:
                bill_dur_s = audio_duration_s(audio_path)
            except FFmpegError as exc:
                raise AdapterError(
                    INPUT_INVALID, f"cannot measure sep input duration: {exc}"
                ) from exc
        cost_cny = _cost_cny_from_output_duration(
            bill_dur_s, reranking_candidates=C.SAM_AUDIO_RERANKING_CANDIDATES
        )

        return {
            "speech_path": speech,
            "non_speech_path": non_speech,
            "cost_cny": cost_cny,
        }


def _download_url(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=300.0)) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise AdapterError(
                        classify_http(resp.status_code),
                        f"sam-audio residual download HTTP {resp.status_code}",
                    )
                tmp = dest.with_suffix(dest.suffix + ".download")
                with tmp.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
                tmp.replace(dest)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"sam-audio residual download: {exc}") from exc


def _cost_cny_from_output_duration(
    dur_s: float, *, reranking_candidates: int = 1
) -> float:
    """fal SAM Audio: $0.05／30s output + $0.025／30s per additional rerank candidate."""
    units = max(1, math.ceil(float(dur_s) / 30.0)) if dur_s > 0 else 1
    usd = units * C.SAM_AUDIO_USD_PER_30S
    extra = max(0, int(reranking_candidates) - 1)
    if extra:
        usd += units * C.SAM_AUDIO_RERANK_USD_PER_30S * extra
    return round(usd * USD_TO_CNY, 8)
