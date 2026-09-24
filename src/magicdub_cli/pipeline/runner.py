"""End-to-end pipeline runner for v0.1.0 (single new task, no resume)."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

from magicdub_cli.errors import StepResult
from magicdub_cli.state.io import recompute_cost_total, save_state, utc_now_iso
from magicdub_cli.steps.fixed import alignment, clipping, demux, duration_fitting, mixing
from magicdub_cli.steps.slots import asr, sep, translation, tts
from magicdub_cli.steps.start import run_start
from magicdub_cli.taskdir import acquire_lock, release_lock


def run_pipeline(*, video: str, src_lang: str, tgt_lang: str) -> int:
    task_root, state, start_result = run_start(video=video, src_lang=src_lang, tgt_lang=tgt_lang)
    if not start_result.ok:
        print(f"error: {start_result.message}", file=sys.stderr)
        return 1

    print(f"task: {task_root}")
    try:
        acquire_lock(task_root, state, "pipeline")
        save_state(task_root, state)

        if not _run_step(task_root, state, "demux", lambda: demux.run(task_root, state)):
            return 1
        if not _run_step(task_root, state, "sep", lambda: sep.run(task_root, state)):
            return 1
        if not _run_step(task_root, state, "asr", lambda: asr.run(task_root, state)):
            return 1
        if not _run_step(task_root, state, "clipping", lambda: clipping.run(task_root, state)):
            return 1
        if not _run_step(
            task_root,
            state,
            "translation",
            lambda: translation.run(task_root, state, attempt=1),
        ):
            return 1

        for sent in state["assets"]["sentences"]:
            sid = sent["id"]
            if not _process_sentence_chain(task_root, state, sid, attempt=1):
                return 1

        if not _run_step(task_root, state, "mixing", lambda: mixing.run(task_root, state)):
            return 1

        # finish
        _mark_step(state, "finish", "running")
        final = state["assets"]["tgt"]
        for key in ("final_video", "final_audio", "srt"):
            ref = final.get(key) or {}
            if not ref.get("path") or not (task_root / ref["path"]).is_file():
                return _fail(task_root, state, "finish", "input_invalid", f"missing {key}")
        if len(state["assets"]["sentences"]) == 0:
            return _fail(task_root, state, "finish", "input_invalid", "no sentences")
        recompute_cost_total(state)
        state["run"]["status"] = "done"
        state["run"]["current_step"] = None
        _mark_step(state, "finish", "done")
        save_state(task_root, state)
        _print_summary(task_root, state)
        return 0
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard
        traceback.print_exc()
        try:
            step = state["run"].get("current_step") or "pipeline"
            return _fail(task_root, state, step, "external_fatal", str(exc))
        except Exception:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 1
    finally:
        try:
            release_lock(task_root, state)
            save_state(task_root, state)
        except Exception:  # noqa: BLE001
            pass


def _process_sentence_chain(
    task_root: Path, state: dict[str, Any], sid: int, *, attempt: int
) -> bool:
    fitting = state["run"]["fitting"]
    lo = float(fitting["lower_ratio"])
    hi = float(fitting["upper_ratio"])
    max_rewrites = int(fitting["max_rewrites"])
    max_attempt = 1 + max_rewrites

    current = attempt
    while True:
        if not _run_step(
            task_root,
            state,
            "tts",
            lambda c=current: tts.run(task_root, state, sentence_id=sid, attempt=c),
        ):
            return False
        if not _run_step(
            task_root,
            state,
            "duration_fitting",
            lambda c=current: duration_fitting.run(task_root, state, sentence_id=sid, attempt=c),
        ):
            return False

        sent = next(s for s in state["assets"]["sentences"] if s["id"] == sid)
        tgt = next(t for t in sent["tgt"] if t["attempt"] == current)
        ratio = float(tgt["fitting_ratio"])

        if lo <= ratio <= hi:
            _select(sent, current, "fitting_pass")
            save_state(task_root, state)
            return _run_step(
                task_root,
                state,
                "alignment",
                lambda: alignment.run(task_root, state, sentence_id=sid),
            )

        if current < max_attempt:
            tgt["selection"] = "rejected"
            save_state(task_root, state)
            next_attempt = current + 1
            if not _run_step(
                task_root,
                state,
                "translation",
                lambda n=next_attempt: translation.run(
                    task_root, state, sentence_ids=[sid], attempt=n
                ),
            ):
                return False
            current = next_attempt
            continue

        # forced: closest to band among all attempts
        best = _closest_attempt(sent, lo, hi)
        _select(sent, best, "forced")
        save_state(task_root, state)
        return _run_step(
            task_root,
            state,
            "alignment",
            lambda: alignment.run(task_root, state, sentence_id=sid),
        )


def _closest_attempt(sent: dict[str, Any], lo: float, hi: float) -> int:
    def distance(ratio: float) -> float:
        if ratio < lo:
            return lo - ratio
        if ratio > hi:
            return ratio - hi
        return 0.0

    candidates = [t for t in sent["tgt"] if t.get("fitting_ratio") is not None]
    candidates.sort(
        key=lambda t: (
            distance(float(t["fitting_ratio"])),
            abs(float(t["fitting_ratio"]) - 1.0),
            int(t["attempt"]),
        )
    )
    return int(candidates[0]["attempt"])


def _select(sent: dict[str, Any], attempt: int, selection: str) -> None:
    for tgt in sent["tgt"]:
        if tgt["attempt"] == attempt:
            tgt["selection"] = selection
        elif tgt.get("selection") != "rejected":
            tgt["selection"] = "rejected"
    sent["selected_attempt"] = attempt


def _run_step(task_root: Path, state: dict[str, Any], name: str, fn) -> bool:
    state["run"]["current_step"] = name
    acquire_lock(task_root, state, name)
    _mark_step(state, name, "running")
    save_state(task_root, state)
    print(f"→ {name}")
    result: StepResult = fn()
    if result.ok:
        _mark_step(state, name, "done")
        save_state(task_root, state)
        return True
    _fail(task_root, state, name, result.error_code or "external_fatal", result.message or "failed")
    return False


def _mark_step(state: dict[str, Any], name: str, status: str) -> None:
    step = state["run"]["steps"].setdefault(name, {})
    step["status"] = status
    now = utc_now_iso()
    if status == "running":
        step["started_at"] = now
        step["finished_at"] = None
        step["error_code"] = None
        step["message"] = None
    elif status == "done":
        step["finished_at"] = now


def _fail(
    task_root: Path,
    state: dict[str, Any],
    step: str,
    code: str,
    message: str,
) -> int:
    state["run"]["status"] = "failed"
    state["run"]["current_step"] = step
    state["run"]["last_error"] = {
        "step": step,
        "error_code": code,
        "message": message,
        "at": utc_now_iso(),
    }
    st = state["run"]["steps"].setdefault(step, {})
    st["status"] = "failed"
    st["error_code"] = code
    st["message"] = message
    st["finished_at"] = utc_now_iso()
    save_state(task_root, state)
    print(f"error [{code}] {step}: {message}", file=sys.stderr)
    return 1


def _print_summary(task_root: Path, state: dict[str, Any]) -> None:
    cost = state["assets"]["cost"]
    print("done")
    print(f"  video: {task_root / state['assets']['tgt']['final_video']['path']}")
    print(f"  audio: {task_root / state['assets']['tgt']['final_audio']['path']}")
    print(f"  srt:   {task_root / state['assets']['tgt']['srt']['path']}")
    print(f"  cost:  ¥{cost['total']:.6f} (ledger entries={len(state['ledger'])})")
    print(
        "  breakdown:"
        f" sep={cost['cost_of_sep']}"
        f" asr={cost['cost_of_asr']}"
        f" tr={cost['cost_of_translation']}"
        f" tts={cost['cost_of_tts']}"
    )
