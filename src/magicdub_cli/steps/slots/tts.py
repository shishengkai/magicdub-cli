"""slot:tts — one sentence, one attempt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.adapters.registry import get_adapter
from magicdub_cli.config import load_credentials, require_credential
from magicdub_cli.errors import (
    ADAPTER_EXHAUSTED,
    INPUT_INVALID,
    AdapterError,
    StepResult,
    fail_result,
    ok_result,
)
from magicdub_cli.media.files import commit, file_ref
from magicdub_cli.state.io import new_ledger_id, recompute_cost_total, save_state, utc_now_iso


def run(task_root: Path, state: dict[str, Any], *, sentence_id: int, attempt: int) -> StepResult:
    sent = next((s for s in state["assets"]["sentences"] if s["id"] == sentence_id), None)
    if sent is None:
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} missing")
    tgt = next((t for t in sent.get("tgt") or [] if t.get("attempt") == attempt), None)
    if tgt is None or not tgt.get("text"):
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} attempt {attempt} text missing")
    ref = sent["src"].get("audio") or {}
    if not ref.get("path"):
        return fail_result(INPUT_INVALID, f"sentence {sentence_id} src.audio missing")

    order = state["run"]["slots"]["tts"]["order"]
    creds = load_credentials()
    tmp = task_root / C.TMP / "tts" / str(sentence_id) / f"attempt_{attempt}"
    last_err: AdapterError | None = None
    for adapter_id in order:
        adapter = get_adapter(adapter_id)
        try:
            api_key = require_credential(creds, "FAL_KEY")
            out = adapter.run(
                {
                    "api_key": api_key,
                    "reference_path": task_root / ref["path"],
                    "text": tgt["text"],
                    "source_text": sent["src"]["text"],
                },
                tmp,
            )
            final = (
                task_root
                / C.MEDIA_SENTENCES
                / str(sentence_id)
                / "tgt"
                / f"attempt_{attempt}.wav"
            )
            commit(Path(out["audio_path"]), final)
            tgt["audio"] = file_ref(final, relative_to=task_root)
            cost = out.get("cost_cny")
            _ledger(state, adapter_id, True, None, cost, None, sentence_id, attempt)
            if cost is not None:
                state["assets"]["cost"]["cost_of_tts"] = float(
                    state["assets"]["cost"].get("cost_of_tts") or 0
                ) + float(cost)
                recompute_cost_total(state)
            save_state(task_root, state)
            return ok_result(adapter_id)
        except AdapterError as exc:
            last_err = exc
            _ledger(
                state,
                adapter_id,
                False,
                exc.code,
                exc.cost_cny,
                exc.message,
                sentence_id,
                attempt,
            )
            save_state(task_root, state)
            continue
    msg = last_err.message if last_err else "tts adapters exhausted"
    return fail_result(ADAPTER_EXHAUSTED, msg)


def _ledger(
    state: dict[str, Any],
    adapter_id: str,
    ok: bool,
    error_code: str | None,
    cost: float | None,
    message: str | None,
    sentence_id: int,
    attempt: int,
) -> None:
    state["ledger"].append(
        {
            "id": new_ledger_id(),
            "at": utc_now_iso(),
            "step": "tts",
            "sentence_id": sentence_id,
            "attempt": attempt,
            "adapter_id": adapter_id,
            "ok": ok,
            "error_code": error_code,
            "cost_cny": cost,
            "message": message,
        }
    )
