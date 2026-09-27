"""fixed:demux — extract audio (prefer stream copy) + silent video copy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, ffprobe_json, run_ffmpeg
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import save_state

# codec_name (ffprobe) → container extension for -c:a copy.
# Unknown / exotic codecs return None → re-encode to float32 WAV.
_CODEC_COPY_EXT: dict[str, str] = {
    "aac": ".m4a",
    "mp3": ".mp3",
    "opus": ".opus",
    "flac": ".flac",
    "vorbis": ".ogg",
    "alac": ".m4a",
    "ac3": ".ac3",
    "eac3": ".eac3",
    "pcm_s16le": ".wav",
    "pcm_s24le": ".wav",
    "pcm_s32le": ".wav",
    "pcm_f32le": ".wav",
    "pcm_f64le": ".wav",
    "pcm_s16be": ".wav",
    "pcm_s24be": ".wav",
    "pcm_s32be": ".wav",
    "pcm_u8": ".wav",
    "pcm_alaw": ".wav",
    "pcm_mulaw": ".wav",
}


def copy_extension_for_codec(codec_name: str | None) -> str | None:
    """Return a demux filename suffix for stream-copy, or None to force WAV."""
    if not codec_name:
        return None
    return _CODEC_COPY_EXT.get(str(codec_name).lower())


def first_audio_stream(probe: dict[str, Any]) -> dict[str, Any] | None:
    for stream in probe.get("streams") or []:
        if stream.get("codec_type") == "audio":
            return stream
    return None


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    video_rel = state["assets"]["src"]["video"].get("path")
    if not video_rel:
        return fail_result(INPUT_INVALID, "src.video missing")
    video = task_root / video_rel
    if not video.is_file():
        return fail_result(INPUT_INVALID, f"video not found: {video_rel}")

    tmp = task_root / C.TMP / "demux"
    tmp.mkdir(parents=True, exist_ok=True)
    tmp_silent = tmp / "silent_video.mp4"

    try:
        probe = ffprobe_json(video)
        audio_stream = first_audio_stream(probe)
        if audio_stream is None:
            return fail_result(INPUT_INVALID, "source video has no audio stream")

        codec = audio_stream.get("codec_name")
        copy_ext = copy_extension_for_codec(codec if isinstance(codec, str) else None)
        tmp_audio = _extract_audio(video, tmp, copy_ext)

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

    final_audio = task_root / C.MEDIA_SRC / f"audio{tmp_audio.suffix.lower()}"
    final_silent = task_root / C.MEDIA_SRC / "silent_video.mp4"
    commit(tmp_audio, final_audio)
    commit(tmp_silent, final_silent)
    state["assets"]["src"]["audio"] = file_ref(final_audio, relative_to=task_root)
    state["assets"]["src"]["silent_video"] = file_ref(final_silent, relative_to=task_root)
    save_state(task_root, state)
    return ok_result()


def _extract_audio(video: Path, tmp: Path, copy_ext: str | None) -> Path:
    """Prefer ``-c:a copy`` into a codec-matched file; fall back to float32 WAV."""
    if copy_ext:
        out = tmp / f"audio{copy_ext}"
        try:
            run_ffmpeg(
                [
                    "-i",
                    str(video),
                    "-vn",
                    "-map",
                    "0:a:0",
                    "-c:a",
                    "copy",
                    str(out),
                ]
            )
            if out.is_file() and out.stat().st_size > 0:
                return out
        except FFmpegError:
            if out.exists():
                out.unlink(missing_ok=True)

    wav = tmp / "audio.wav"
    run_ffmpeg(
        [
            "-i",
            str(video),
            "-vn",
            "-map",
            "0:a:0",
            "-c:a",
            "pcm_f32le",
            str(wav),
        ]
    )
    return wav
