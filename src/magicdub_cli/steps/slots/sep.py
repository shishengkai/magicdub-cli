"""slot:sep"""

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
from magicdub_cli.state.io import apply_adapter_cost, new_ledger_id, save_state, utc_now_iso


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    audio = state["assets"]["src"]["audio"]
    if not audio.get("path"):
        return fail_result(INPUT_INVALID, "src.audio missing")
    order = state["run"]["slots"]["sep"]["order"]
    creds = load_credentials()
    tmp = task_root / C.TMP / "sep"
    last_err: AdapterError | None = None
    for adapter_id in order:
        adapter = get_adapter(adapter_id)
        try:
            if adapter_id.startswith("mvsep/"):
                api_key = require_credential(creds, "MVSEP_API_KEY")
                fal_key = require_credential(creds, "FAL_KEY")
                run_inputs: dict[str, Any] = {
                    "api_key": api_key,
                    "fal_key": fal_key,
                    "audio_path": task_root / audio["path"],
                }
            else:
                api_key = require_credential(creds, "FAL_KEY")
                run_inputs = {
                    "api_key": api_key,
                    "audio_path": task_root / audio["path"],
                }
            out = adapter.run(run_inputs, tmp)
            speech_tmp = Path(out["speech_path"])
            non_tmp = Path(out["non_speech_path"])
            speech_final = task_root / C.MEDIA_SRC / f"speech{speech_tmp.suffix}"
            non_final = task_root / C.MEDIA_SRC / f"non_speech{non_tmp.suffix}"
            commit(speech_tmp, speech_final)
            commit(non_tmp, non_final)
            state["assets"]["src"]["speech"] = file_ref(speech_final, relative_to=task_root)
            state["assets"]["src"]["non_speech"] = file_ref(non_final, relative_to=task_root)
            cost = out.get("cost_cny")
            _ledger(state, adapter_id, True, None, cost, None)
            apply_adapter_cost(state, "cost_of_sep", cost)
            save_state(task_root, state)
            return ok_result(adapter_id)
        except AdapterError as exc:
            last_err = exc
            _ledger(state, adapter_id, False, exc.code, exc.cost_cny, exc.message)
            save_state(task_root, state)
            continue
    msg = last_err.message if last_err else "sep adapters exhausted"
    code = last_err.code if last_err else ADAPTER_EXHAUSTED
    return fail_result(code if code != ADAPTER_EXHAUSTED else ADAPTER_EXHAUSTED, msg)


def _ledger(
    state: dict[str, Any],
    adapter_id: str,
    ok: bool,
    error_code: str | None,
    cost: float | None,
    message: str | None,
) -> None:
    state["ledger"].append(
        {
            "id": new_ledger_id(),
            "at": utc_now_iso(),
            "step": "sep",
            "sentence_id": None,
            "attempt": None,
            "adapter_id": adapter_id,
            "ok": ok,
            "error_code": error_code,
            "cost_cny": cost,
            "message": message,
        }
    )
