"""fixed:alignment — atempo stretch selected attempt to src.audio_duration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.ffmpeg_util import FFmpegError, audio_duration_ms, run_ffmpeg
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import save_state


def run(task_root: Path, state: dict[str, Any], *, sentence_id: int) -> StepResult:
    sent = next((s for s in state["assets"]["sentences"] if s["id"] == sentence_id), None)
    if sent is None:
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} missing")
    attempt = sent.get("selected_attempt")
    if attempt is None:
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} selected_attempt missing")
    tgt = next((t for t in sent.get("tgt") or [] if t.get("attempt") == attempt), None)
    if tgt is None or not (tgt.get("audio") or {}).get("path"):
        return fail_result(INPUT_INVALID, f"selected attempt audio missing for {sentence_id}")
    target_ms = int(sent["src"]["audio_duration"])
    src_path = task_root / tgt["audio"]["path"]
    try:
        actual_ms = audio_duration_ms(src_path)
    except FFmpegError as exc:
        return fail_result(INPUT_INVALID, str(exc))

    tmp = task_root / C.TMP / "alignment" / str(sentence_id)
    tmp.mkdir(parents=True, exist_ok=True)
    out_tmp = tmp / f"attempt_{attempt}.aligned.wav"

    if actual_ms <= 0:
        return fail_result(INPUT_INVALID, "tts duration is 0")
    # ratio for atempo = actual/target means speed up if actual > target
    speed = actual_ms / float(target_ms)
    filters = _atempo_chain(speed)
    try:
        args = ["-i", str(src_path)]
        if filters:
            args += ["-filter:a", ",".join(filters)]
        args += ["-c:a", "pcm_f32le", str(out_tmp)]
        run_ffmpeg(args)
        # trim/pad to exact target if still off
        aligned_ms = audio_duration_ms(out_tmp)
        if abs(aligned_ms - target_ms) > C.ALIGNMENT_TOLERANCE_MS:
            exact = tmp / "exact.wav"
            run_ffmpeg(
                [
                    "-i",
                    str(out_tmp),
                    "-af",
                    f"apad,atrim=duration={target_ms / 1000.0:.6f}",
                    "-c:a",
                    "pcm_f32le",
                    str(exact),
                ]
            )
            out_tmp = exact
            aligned_ms = audio_duration_ms(out_tmp)
        if abs(aligned_ms - target_ms) > C.ALIGNMENT_TOLERANCE_MS:
            return fail_result(
                INPUT_INVALID,
                f"alignment tolerance exceeded: {aligned_ms} vs {target_ms}",
            )
    except FFmpegError as exc:
        return fail_result(INPUT_INVALID, str(exc))

    final = (
        task_root
        / C.MEDIA_SENTENCES
        / str(sentence_id)
        / "tgt"
        / f"attempt_{attempt}.aligned.wav"
    )
    commit(out_tmp, final)
    tgt["aligned_audio"] = file_ref(final, relative_to=task_root)
    save_state(task_root, state)
    return ok_result()


def _atempo_chain(speed: float) -> list[str]:
    """Build atempo filters; each factor in [0.5, 2.0]."""
    if abs(speed - 1.0) < 1e-6:
        return []
    factors: list[float] = []
    remaining = speed
    # atempo changes playback speed; chain until remaining in range
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return [f"atempo={f:.6f}" for f in factors]
