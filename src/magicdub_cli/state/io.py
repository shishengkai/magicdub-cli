"""Atomic state.json load/save and skeleton builders."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ulid import ULID

from magicdub_cli import constants as C


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def empty_file_ref() -> dict[str, Any]:
    return {"path": None, "sha256": None, "size_bytes": None}


def empty_cost() -> dict[str, Any]:
    return {
        "cost_of_sep": 0.0,
        "cost_of_asr": 0.0,
        "cost_of_translation": 0.0,
        "cost_of_tts": 0.0,
        "total": 0.0,
    }


def empty_step_status() -> dict[str, Any]:
    return {
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "input_fingerprint": None,
        "error_code": None,
        "message": None,
    }


STEP_NAMES = [
    "start",
    "demux",
    "sep",
    "asr",
    "clipping",
    "translation",
    "tts",
    "duration_fitting",
    "alignment",
    "mixing",
    "finish",
]


def new_state(
    *,
    task_id: str,
    title: str,
    src_language: str,
    tgt_language: str,
    fitting: dict[str, Any],
    slots: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema_version": C.SCHEMA_VERSION,
        "engine": C.ENGINE,
        "task_id": task_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "program": {"name": C.PROGRAM_NAME, "version": C.VERSION},
        "run": {
            "status": "pending",
            "current_step": None,
            "cursor": {"sentence_id": None, "phase": None},
            "fitting": dict(fitting),
            "slots": {k: {"order": list(v["order"])} for k, v in slots.items()},
            "steps": {name: empty_step_status() for name in STEP_NAMES},
            "lock": {"holder": None, "step": None, "acquired_at": None},
            "last_error": {
                "step": None,
                "error_code": None,
                "message": None,
                "at": None,
            },
        },
        "assets": {
            "src": {
                "language": src_language,
                "video": empty_file_ref(),
                "audio": empty_file_ref(),
                "silent_video": empty_file_ref(),
                "speech": empty_file_ref(),
                "non_speech": empty_file_ref(),
                "transcript": None,
            },
            "sentences": [],
            "tgt": {
                "language": tgt_language,
                "final_video": empty_file_ref(),
                "final_audio": empty_file_ref(),
                "srt": empty_file_ref(),
            },
            "cost": empty_cost(),
        },
        "ledger": [],
    }


def load_state(task_root: Path) -> dict[str, Any]:
    path = task_root / C.STATE_FILENAME
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("engine") != C.ENGINE:
        raise ValueError(f"not a {C.ENGINE} task: engine={data.get('engine')!r}")
    return data


def save_state(task_root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now_iso()
    path = task_root / C.STATE_FILENAME
    tmp = path.with_suffix(".json.tmp")
    text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def new_task_id() -> str:
    return str(ULID())


def new_ledger_id() -> str:
    return str(ULID())


def recompute_cost_total(state: dict[str, Any]) -> None:
    cost = state["assets"]["cost"]
    total = (
        float(cost.get("cost_of_sep") or 0)
        + float(cost.get("cost_of_asr") or 0)
        + float(cost.get("cost_of_translation") or 0)
        + float(cost.get("cost_of_tts") or 0)
    )
    cost["total"] = round(total, 8)


def apply_adapter_cost(state: dict[str, Any], bucket: str, cost_cny: float | None) -> None:
    """Accumulate adapter ``cost_cny`` into ``assets.cost[bucket]`` and refresh total."""
    if cost_cny is None:
        return
    cost = state["assets"]["cost"]
    cost[bucket] = float(cost.get(bucket) or 0) + float(cost_cny)
    recompute_cost_total(state)
