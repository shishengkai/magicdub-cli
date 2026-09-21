"""fixed:demux — split video into float32 WAV audio and silent video copy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, run_ffmpeg
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import save_state


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    video_rel = state["assets"]["src"]["video"].get("path")
    if not video_rel:
        return fail_result(INPUT_INVALID, "src.video missing")
    video = task_root / video_rel
    if not video.is_file():
        return fail_result(INPUT_INVALID, f"video not found: {video_rel}")

    tmp = task_root / C.TMP / "demux"
    tmp.mkdir(parents=True, exist_ok=True)
    tmp_audio = tmp / "audio.wav"
    tmp_silent = tmp / "silent_video.mp4"

    try:
        # Fail clearly if the container has no audio stream.
        from magicdub_cli.ffmpeg_util import ffprobe_json

        streams = ffprobe_json(video).get("streams") or []
        if not any(s.get("codec_type") == "audio" for s in streams):
            return fail_result(INPUT_INVALID, "source video has no audio stream")
        run_ffmpeg(
            [
                "-i",
                str(video),
                "-vn",
                "-map",
                "0:a:0",
                "-c:a",
                "pcm_f32le",
                str(tmp_audio),
            ]
        )
        run_ffmpeg(
            [
                "-i",
                str(video),
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp_silent),
            ]
        )
    except FFmpegError as exc:
        return fail_result(INPUT_INVALID, str(exc))

    if not tmp_audio.is_file():
        return fail_result(INPUT_INVALID, "demux produced no audio track")

    final_audio = task_root / C.MEDIA_SRC / "audio.wav"
    final_silent = task_root / C.MEDIA_SRC / "silent_video.mp4"
    commit(tmp_audio, final_audio)
    commit(tmp_silent, final_silent)
    state["assets"]["src"]["audio"] = file_ref(final_audio, relative_to=task_root)
    state["assets"]["src"]["silent_video"] = file_ref(final_silent, relative_to=task_root)
    save_state(task_root, state)
    return ok_result()
