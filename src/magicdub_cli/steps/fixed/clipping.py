"""fixed:clipping — cut per-sentence refs; audio_duration := end_ms - start_ms."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, run_ffmpeg
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import save_state


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    speech = state["assets"]["src"]["speech"]
    if not speech.get("path"):
        return fail_result(INPUT_INVALID, "src.speech missing")
    speech_path = task_root / speech["path"]
    tmp = task_root / C.TMP / "clipping"
    tmp.mkdir(parents=True, exist_ok=True)

    for sent in state["assets"]["sentences"]:
        sid = sent["id"]
        start_ms = int(sent["start_ms"])
        end_ms = int(sent["end_ms"])
        window = end_ms - start_ms
        if window <= 0:
            return fail_result(INPUT_INVALID, f"sentence {sid} window <= 0")
        start_s = start_ms / 1000.0
        dur_s = window / 1000.0
        tmp_wav = tmp / f"{sid}.wav"
        try:
            run_ffmpeg(
                [
                    "-i",
                    str(speech_path),
                    "-ss",
                    f"{start_s:.3f}",
                    "-t",
                    f"{dur_s:.3f}",
                    "-c:a",
                    "pcm_f32le",
                    str(tmp_wav),
                ]
            )
        except FFmpegError as exc:
            return fail_result(INPUT_INVALID, f"clip sentence {sid}: {exc}")
        final = task_root / C.MEDIA_SENTENCES / str(sid) / "src.wav"
        commit(tmp_wav, final)
        sent["src"]["audio"] = file_ref(final, relative_to=task_root)
        sent["src"]["audio_duration"] = window

    save_state(task_root, state)
    return ok_result()
