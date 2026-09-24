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
from magicdub_cli.state.io import new_ledger_id, recompute_cost_total, save_state, utc_now_iso


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
    if sentence_ids is None:
        batch = list(sentences_all)
    else:
        idset = set(sentence_ids)
        batch = [s for s in sentences_all if s["id"] in idset]
    if not batch:
        return fail_result(INPUT_INVALID, "no sentences for translation")

    payload_sentences = []
    for sent in batch:
        history = []
        if attempt >= 2:
            for tgt in sent.get("tgt") or []:
                if tgt.get("selection") == "rejected" and tgt.get("audio_duration") is not None:
                    history.append(
                        {
                            "attempt": tgt["attempt"],
                            "text": tgt["text"],
                            "tts_duration_ms": tgt["audio_duration"],
                            "fitting_ratio": tgt.get("fitting_ratio"),
                        }
                    )
        payload_sentences.append(
            {
                "id": sent["id"],
                "src_text": sent["src"]["text"],
                "target_duration_ms": sent["src"]["audio_duration"],
                "attempt": attempt,
                "history": history,
            }
        )

    order = state["run"]["slots"]["translation"]["order"]
    creds = load_credentials()
    tmp = task_root / C.TMP / "translation"
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
                    "max_attempt": max_attempt,
                },
                tmp,
            )
            by_id = {int(t["id"]): t["text"] for t in out["translations"]}
            for sent in batch:
                text = by_id.get(sent["id"])
                if text is None or not str(text).strip():
                    return fail_result(
                        INPUT_INVALID,
                        f"missing translation for sentence {sent['id']}",
                    )
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
                    "aligned_audio": {"path": None, "sha256": None, "size_bytes": None},
                }
                if existing is not None:
                    existing.update(entry)
                else:
                    tgt_list.append(entry)

            cost = out.get("cost_cny")
            _ledger(state, adapter_id, True, None, cost, None, attempt)
            if cost is not None:
                state["assets"]["cost"]["cost_of_translation"] = float(
                    state["assets"]["cost"].get("cost_of_translation") or 0
                ) + float(cost)
                recompute_cost_total(state)
            save_state(task_root, state)
            return ok_result(adapter_id)
        except AdapterError as exc:
            last_err = exc
            _ledger(state, adapter_id, False, exc.code, exc.cost_cny, exc.message, attempt)
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
