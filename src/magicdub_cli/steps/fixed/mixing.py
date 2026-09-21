"""fixed:mixing — timeline mix + silent video mux + SRT + metadata strip."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, media_duration_ms, run_ffmpeg
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import save_state


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    sentences = state["assets"]["sentences"]
    for sent in sentences:
        att = sent.get("selected_attempt")
        if att is None:
            return fail_result(INPUT_INVALID, f"sentence {sent['id']} missing selected_attempt")
        tgt = next((t for t in sent["tgt"] if t.get("attempt") == att), None)
        if tgt is None or not (tgt.get("aligned_audio") or {}).get("path"):
            return fail_result(INPUT_INVALID, f"sentence {sent['id']} missing aligned_audio")

    non_speech = state["assets"]["src"]["non_speech"]
    silent = state["assets"]["src"]["silent_video"]
    if not non_speech.get("path") or not silent.get("path"):
        return fail_result(INPUT_INVALID, "non_speech or silent_video missing")

    tmp = task_root / C.TMP / "mixing"
    tmp.mkdir(parents=True, exist_ok=True)
    mix_wav = tmp / "final.wav"
    mix_mp4 = tmp / "final.mp4"
    mix_srt = tmp / "final.srt"

    try:
        duration_ms = media_duration_ms(task_root / silent["path"])
        _mix_audio(task_root, state, non_speech["path"], mix_wav, duration_ms)
        _mux_video(task_root, silent["path"], mix_wav, mix_mp4, duration_ms)
        _write_srt(state, mix_srt)
    except (FFmpegError, OSError, ValueError) as exc:
        return fail_result(INPUT_INVALID, str(exc))

    exports = task_root / C.EXPORTS
    final_wav = exports / "final.wav"
    final_mp4 = exports / "final.mp4"
    final_srt = exports / "final.srt"
    commit(mix_wav, final_wav)
    commit(mix_mp4, final_mp4)
    commit(mix_srt, final_srt)
    state["assets"]["tgt"]["final_audio"] = file_ref(final_wav, relative_to=task_root)
    state["assets"]["tgt"]["final_video"] = file_ref(final_mp4, relative_to=task_root)
    state["assets"]["tgt"]["srt"] = file_ref(final_srt, relative_to=task_root)
    save_state(task_root, state)
    return ok_result()


def _mix_audio(
    task_root: Path,
    state: dict[str, Any],
    non_speech_rel: str,
    out_path: Path,
    duration_ms: int,
) -> None:
    sentences = sorted(state["assets"]["sentences"], key=lambda s: s["start_ms"])
    inputs = ["-i", str(task_root / non_speech_rel)]
    filters = [
        f"[0:a]aresample={C.FINAL_WAV_SAMPLE_RATE},"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad,atrim=duration={duration_ms / 1000.0:.6f}[a0]"
    ]
    labels = ["[a0]"]
    for i, sent in enumerate(sentences, start=1):
        att = sent["selected_attempt"]
        tgt = next(t for t in sent["tgt"] if t["attempt"] == att)
        path = task_root / tgt["aligned_audio"]["path"]
        inputs += ["-i", str(path)]
        delay = int(sent["start_ms"])
        filters.append(
            f"[{i}:a]aresample={C.FINAL_WAV_SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay}|{delay}[a{i}]"
        )
        labels.append(f"[a{i}]")
    n = len(labels)
    filters.append(
        "".join(labels)
        + f"amix=inputs={n}:duration=longest:normalize=0,"
        f"alimiter=limit=0.98:attack=2:release=50[out]"
    )
    run_ffmpeg(
        [
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:a",
            "pcm_f32le",
            "-ar",
            str(C.FINAL_WAV_SAMPLE_RATE),
            "-ac",
            "2",
            str(out_path),
        ]
    )


def _mux_video(
    task_root: Path,
    silent_rel: str,
    audio_path: Path,
    out_path: Path,
    duration_ms: int,
) -> None:
    run_ffmpeg(
        [
            "-i",
            str(task_root / silent_rel),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration_ms / 1000.0:.6f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            C.FINAL_AAC_BITRATE,
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-movflags",
            "+faststart+disable_chpl",
            str(out_path),
        ]
    )


def _write_srt(state: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    ordered = sorted(state["assets"]["sentences"], key=lambda s: s["start_ms"])
    for i, sent in enumerate(ordered, start=1):
        att = sent["selected_attempt"]
        tgt = next(t for t in sent["tgt"] if t["attempt"] == att)
        text = _srt_text(tgt["text"])
        lines.append(str(i))
        lines.append(f"{_ts(sent['start_ms'])} --> {_ts(sent['end_ms'])}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _ts(ms: int) -> str:
    if ms < 0:
        ms = 0
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    milli = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _srt_text(text: str) -> str:
    # Replace ,，。 and non-decimal '.' with half-width space; keep ?! and decimals.
    out = []
    for i, ch in enumerate(text):
        if ch in ",，。":
            # keep '.' if looks like decimal: digit . digit
            out.append(" ")
        elif ch == ".":
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if prev.isdigit() and nxt.isdigit():
                out.append(".")
            else:
                out.append(" ")
        else:
            out.append(ch)
    cleaned = re.sub(r" +", " ", "".join(out)).strip()
    return cleaned
