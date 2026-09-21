"""fal/index-tts-2 with short-reference tail silence pad."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import INPUT_INVALID, AdapterError
from magicdub_cli.fal_api import run_model, upload_file
from magicdub_cli.ffmpeg_util import FFmpegError, run_ffmpeg


class IndexTTS2Adapter(Adapter):
    adapter_id = "fal/index-tts-2"
    endpoint = "fal-ai/index-tts-2/text-to-speech"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        api_key = inputs["api_key"]
        ref_path = Path(inputs["reference_path"])
        text = inputs["text"]
        source_text = inputs.get("source_text") or ""
        tmp_dir.mkdir(parents=True, exist_ok=True)

        ref = _maybe_pad_reference(ref_path, tmp_dir, source_text=source_text)
        url = upload_file(ref, api_key)
        out = tmp_dir / "tts.wav"
        _result, cost = run_model(
            endpoint=self.endpoint,
            payload={
                "audio_url": url,
                "emotional_audio_url": url,
                "prompt": text,
            },
            api_key=api_key,
            download_to=out,
            result_key="audio",
        )
        if not out.is_file():
            raise AdapterError("external_fatal", "index-tts-2 produced no audio")
        final = tmp_dir / "tts_f32.wav"
        try:
            run_ffmpeg(["-i", str(out), "-c:a", "pcm_f32le", str(final)])
        except FFmpegError as exc:
            raise AdapterError(INPUT_INVALID, str(exc)) from exc
        return {"audio_path": final, "cost_cny": cost}


def _maybe_pad_reference(ref_path: Path, tmp_dir: Path, *, source_text: str) -> Path:
    work = tmp_dir / "ref_measure.wav"
    try:
        run_ffmpeg(["-i", str(ref_path), "-ac", "1", "-c:a", "pcm_s16le", str(work)])
    except FFmpegError as exc:
        raise AdapterError(INPUT_INVALID, str(exc)) from exc

    with wave.open(str(work), "rb") as wf:
        rate = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return ref_path
    duration = len(samples) / float(rate)
    if duration >= C.INDEX_TTS_MIN_REF_SEC:
        return ref_path
    if not any(ch.isalnum() for ch in source_text):
        return ref_path
    # RMS of int16
    acc = 0.0
    for s in samples:
        v = s / 32768.0
        acc += v * v
    rms = math.sqrt(acc / len(samples))
    if rms < 1e-5:
        return ref_path
    target_frames = int(math.ceil(C.INDEX_TTS_PAD_TO_SEC * rate))
    if len(samples) >= target_frames:
        return ref_path
    samples.extend([0] * (target_frames - len(samples)))
    out = tmp_dir / "ref_padded.wav"
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return out
