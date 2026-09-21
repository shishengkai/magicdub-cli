"""fixed:duration_fitting — probe TTS duration and ratio only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, audio_duration_ms
from magicdub_cli.state.io import save_state


def run(task_root: Path, state: dict[str, Any], *, sentence_id: int, attempt: int) -> StepResult:
    sent = next((s for s in state["assets"]["sentences"] if s["id"] == sentence_id), None)
    if sent is None:
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} missing")
    tgt = next((t for t in sent.get("tgt") or [] if t.get("attempt") == attempt), None)
    if tgt is None or not (tgt.get("audio") or {}).get("path"):
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} attempt {attempt} audio missing")
    src_dur = sent["src"].get("audio_duration")
    if not src_dur:
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} src.audio_duration missing")
    try:
        tts_dur = audio_duration_ms(task_root / tgt["audio"]["path"])
    except FFmpegError as exc:
        return fail_result(INPUT_INVALID, str(exc))
    ratio = tts_dur / float(src_dur)
    tgt["audio_duration"] = tts_dur
    tgt["fitting_ratio"] = ratio
    save_state(task_root, state)
    return ok_result()
