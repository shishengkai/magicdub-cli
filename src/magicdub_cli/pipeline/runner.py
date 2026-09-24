"""End-to-end pipeline runner (single new task, no resume).

Fitting loop is round-based and serial by phase within each round:
  batch translation → all TTS for the round → all duration_fitting → mark selection
  → batch retranslate all rejected (up to max_rewrites) → then per-sentence alignment.
"""

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

        if not _run_fitting_rounds(task_root, state):
            return 1

        for sent in state["assets"]["sentences"]:
            sid = sent["id"]
            if not _run_step(
                task_root,
                state,
                "alignment",
                lambda s=sid: alignment.run(task_root, state, sentence_id=s),
            ):
                return 1

        if not _run_step(task_root, state, "mixing", lambda: mixing.run(task_root, state)):
            return 1

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


def _run_fitting_rounds(task_root: Path, state: dict[str, Any]) -> bool:
    """Round-based: all TTS, then all duration_fitting/selection, then batch rewrite."""
    lo, hi, max_attempt = fitting_limits(state)

    for attempt in range(1, max_attempt + 1):
        pending_ids = sentence_ids_for_attempt(state, attempt)
        if not pending_ids:
            break

        print(f"fitting round attempt={attempt} sentences={pending_ids}")
        for sid in pending_ids:
            if not _run_step(
                task_root,
                state,
                "tts",
                lambda s=sid, a=attempt: tts.run(
                    task_root, state, sentence_id=s, attempt=a
                ),
            ):
                return False

        for sid in pending_ids:
            if not _run_step(
                task_root,
                state,
                "duration_fitting",
                lambda s=sid, a=attempt: duration_fitting.run(
                    task_root, state, sentence_id=s, attempt=a
                ),
            ):
                return False
            apply_attempt_selection(state, sentence_id=sid, attempt=attempt, lo=lo, hi=hi)
            save_state(task_root, state)

        rejected_ids = unsettled_sentence_ids(state)
        if not rejected_ids:
            break

        if attempt < max_attempt:
            next_attempt = attempt + 1
            if not _run_step(
                task_root,
                state,
                "translation",
                lambda ids=list(rejected_ids), n=next_attempt: translation.run(
                    task_root, state, sentence_ids=ids, attempt=n
                ),
            ):
                return False
            continue

        for sid in rejected_ids:
            sent = next(s for s in state["assets"]["sentences"] if s["id"] == sid)
            best = closest_attempt(sent, lo, hi)
            select_attempt(sent, best, "forced")
        save_state(task_root, state)

    return True


def fitting_limits(state: dict[str, Any]) -> tuple[float, float, int]:
    fitting = state["run"]["fitting"]
    lo = float(fitting["lower_ratio"])
    hi = float(fitting["upper_ratio"])
    max_attempt = 1 + int(fitting["max_rewrites"])
    return lo, hi, max_attempt


def sentence_ids_for_attempt(state: dict[str, Any], attempt: int) -> list[int]:
    """Unsettled sentences that already have text for this attempt."""
    ids: list[int] = []
    for sent in state["assets"]["sentences"]:
        if sent.get("selected_attempt") is not None:
            continue
        tgt = next(
            (t for t in sent.get("tgt") or [] if t.get("attempt") == attempt and t.get("text")),
            None,
        )
        if tgt is not None:
            ids.append(int(sent["id"]))
    return ids


def unsettled_sentence_ids(state: dict[str, Any]) -> list[int]:
    return [
        int(s["id"])
        for s in state["assets"]["sentences"]
        if s.get("selected_attempt") is None
    ]


def apply_attempt_selection(
    state: dict[str, Any], *, sentence_id: int, attempt: int, lo: float, hi: float
) -> str:
    """Mark fitting_pass or rejected for this attempt. Returns selection label."""
    sent = next(s for s in state["assets"]["sentences"] if s["id"] == sentence_id)
    tgt = next(t for t in sent["tgt"] if t["attempt"] == attempt)
    ratio = float(tgt["fitting_ratio"])
    if lo <= ratio <= hi:
        select_attempt(sent, attempt, "fitting_pass")
        return "fitting_pass"
    tgt["selection"] = "rejected"
    return "rejected"


def closest_attempt(sent: dict[str, Any], lo: float, hi: float) -> int:
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


def select_attempt(sent: dict[str, Any], attempt: int, selection: str) -> None:
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
