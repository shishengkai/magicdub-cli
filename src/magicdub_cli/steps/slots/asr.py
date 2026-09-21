"""slot:asr"""

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
from magicdub_cli.state.io import new_ledger_id, recompute_cost_total, save_state, utc_now_iso


def run(task_root: Path, state: dict[str, Any]) -> StepResult:
    speech = state["assets"]["src"]["speech"]
    if not speech.get("path"):
        return fail_result(INPUT_INVALID, "src.speech missing")
    order = state["run"]["slots"]["asr"]["order"]
    creds = load_credentials()
    tmp = task_root / C.TMP / "asr"
    last_err: AdapterError | None = None
    for adapter_id in order:
        adapter = get_adapter(adapter_id)
        try:
            api_key = require_credential(creds, "FAL_KEY")
            out = adapter.run(
                {
                    "api_key": api_key,
                    "speech_path": task_root / speech["path"],
                    "language": state["assets"]["src"]["language"],
                },
                tmp,
            )
            raw_sentences = out.get("sentences") or []
            if not raw_sentences:
                return fail_result(INPUT_INVALID, "ASR returned 0 sentences")
            sentences = []
            for i, s in enumerate(raw_sentences, start=1):
                text = (s.get("text") or "").strip()
                if not text:
                    return fail_result(INPUT_INVALID, f"ASR sentence {i} has empty text")
                sentences.append(
                    {
                        "id": i,
                        "start_ms": int(s["start_ms"]),
                        "end_ms": int(s["end_ms"]),
                        "speaker_id": str(s.get("speaker_id") or "SPEAKER_00"),
                        "selected_attempt": None,
                        "src": {
                            "text": text,
                            "audio": {"path": None, "sha256": None, "size_bytes": None},
                            "audio_duration": None,
                        },
                        "tgt": [],
                    }
                )
            state["assets"]["src"]["transcript"] = out.get("transcript") or ""
            state["assets"]["sentences"] = sentences
            cost = out.get("cost_cny")
            _ledger(state, adapter_id, True, None, cost, None)
            if cost is not None:
                state["assets"]["cost"]["cost_of_asr"] = float(
                    state["assets"]["cost"].get("cost_of_asr") or 0
                ) + float(cost)
                recompute_cost_total(state)
            save_state(task_root, state)
            return ok_result(adapter_id)
        except AdapterError as exc:
            last_err = exc
            _ledger(state, adapter_id, False, exc.code, exc.cost_cny, exc.message)
            save_state(task_root, state)
            continue
    msg = last_err.message if last_err else "asr adapters exhausted"
    return fail_result(ADAPTER_EXHAUSTED, msg)


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
            "step": "asr",
            "sentence_id": None,
            "attempt": None,
            "adapter_id": adapter_id,
            "ok": ok,
            "error_code": error_code,
            "cost_cny": cost,
            "message": message,
        }
    )
