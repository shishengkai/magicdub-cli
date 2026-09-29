"""slot:translation"""

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
from magicdub_cli.state.io import apply_adapter_cost, new_ledger_id, save_state, utc_now_iso
from magicdub_cli.steps.slots.translation_context import build_context, validate_translations


def run(
    task_root: Path,
    state: dict[str, Any],
    *,
    sentence_ids: list[int] | None = None,
    attempt: int = 1,
) -> StepResult:
    transcript = state["assets"]["src"].get("transcript")
    if not transcript:
        return fail_result(INPUT_INVALID, "src.transcript missing")
    sentences_all = state["assets"]["sentences"]
    try:
        document, payload_sentences = build_context(
            sentences_all,
            sentence_ids=sentence_ids,
            attempt=attempt,
            fitting=state["run"]["fitting"],
        )
    except ValueError as exc:
        return fail_result(INPUT_INVALID, str(exc))
    expected_ids = {s["id"] for s in payload_sentences}
    batch = [s for s in sentences_all if s["id"] in expected_ids]

    order = state["run"]["slots"]["translation"]["order"]
    creds = load_credentials()
    tmp = task_root / C.TMP / "translation" / f"attempt_{attempt}"
    max_attempt = 1 + int(state["run"]["fitting"]["max_rewrites"])
    last_err: AdapterError | None = None
    for adapter_id in order:
        adapter = get_adapter(adapter_id)
        try:
            api_key = require_credential(creds, "DEEPSEEK_API_KEY")
            out = adapter.run(
                {
                    "api_key": api_key,
                    "transcript": transcript,
                    "src_language": state["assets"]["src"]["language"],
                    "tgt_language": state["assets"]["tgt"]["language"],
                    "sentences": payload_sentences,
                    "document": document,
                    "fitting": dict(state["run"]["fitting"]),
                    "max_attempt": max_attempt,
                },
                tmp,
            )
            cost = out.get("cost_cny")
            try:
                by_id = validate_translations(out.get("translations"), expected_ids)
            except ValueError as exc:
                _ledger(state, adapter_id, False, INPUT_INVALID, cost, str(exc), attempt)
                apply_adapter_cost(state, "cost_of_translation", cost)
                save_state(task_root, state)
                return fail_result(INPUT_INVALID, str(exc))
            for sent in batch:
                text = by_id[sent["id"]]
                # replace or append attempt entry
                tgt_list = sent.setdefault("tgt", [])
                existing = next((t for t in tgt_list if t.get("attempt") == attempt), None)
                entry = {
                    "attempt": attempt,
                    "text": str(text).strip(),
                    "audio": {"path": None, "sha256": None, "size_bytes": None},
                    "audio_duration": None,
                    "fitting_ratio": None,
                    "selection": None,
                    "translation_prompt_version": out.get("prompt_version"),
                    "aligned_audio": {"path": None, "sha256": None, "size_bytes": None},
                }
                if existing is not None:
                    existing.update(entry)
                else:
                    tgt_list.append(entry)

            _ledger(state, adapter_id, True, None, cost, None, attempt)
            apply_adapter_cost(state, "cost_of_translation", cost)
            save_state(task_root, state)
            return ok_result(adapter_id)
        except AdapterError as exc:
            last_err = exc
            _ledger(state, adapter_id, False, exc.code, exc.cost_cny, exc.message, attempt)
            apply_adapter_cost(state, "cost_of_translation", exc.cost_cny)
            save_state(task_root, state)
            continue
    msg = last_err.message if last_err else "translation adapters exhausted"
    return fail_result(ADAPTER_EXHAUSTED, msg)


def _ledger(
    state: dict[str, Any],
    adapter_id: str,
    ok: bool,
    error_code: str | None,
    cost: float | None,
    message: str | None,
    attempt: int,
) -> None:
    state["ledger"].append(
        {
            "id": new_ledger_id(),
            "at": utc_now_iso(),
            "step": "translation",
            "sentence_id": None,
            "attempt": attempt,
            "adapter_id": adapter_id,
            "ok": ok,
            "error_code": error_code,
            "cost_cny": cost,
            "message": message,
        }
    )
