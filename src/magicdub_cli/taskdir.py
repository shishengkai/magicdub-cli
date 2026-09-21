"""Task root creation and process lock (run.lock file + state mirror)."""

from __future__ import annotations

import json
import os
import platform
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.config import sanitize_stem
from magicdub_cli.state.io import utc_now_iso


def create_task_dir(projects_dir: Path, video_path: Path) -> tuple[Path, str]:
    """Create <stem>_<YYYYMMDD_HHMMSS>/ under projects_dir. Returns (root, title)."""
    projects_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_stem(video_path.name)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{stem}_{stamp}"
    root = projects_dir / name
    if root.exists():
        suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        root = projects_dir / f"{name}_{suffix}"
    root.mkdir(parents=False)
    for sub in (C.MEDIA_SRC, C.MEDIA_SENTENCES, C.EXPORTS, C.TMP):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root, stem


def lock_path(task_root: Path) -> Path:
    return task_root / C.LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _parse_holder(holder: str) -> tuple[str, int] | None:
    if ":" not in holder:
        return None
    host, _, pid_s = holder.rpartition(":")
    try:
        return host, int(pid_s)
    except ValueError:
        return None


def read_lock_file(task_root: Path) -> dict[str, Any] | None:
    path = lock_path(task_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear_lock(task_root: Path, state: dict[str, Any] | None = None) -> None:
    path = lock_path(task_root)
    if path.exists():
        path.unlink()
    if state is not None:
        state["run"]["lock"] = {"holder": None, "step": None, "acquired_at": None}


def acquire_lock(task_root: Path, state: dict[str, Any], step: str) -> None:
    """Acquire run.lock. Clears same-host dead pid; rejects live other pid / other host."""
    existing = read_lock_file(task_root)
    hostname = platform.node() or "localhost"
    my_holder = f"{hostname}:{os.getpid()}"
    if existing and existing.get("holder"):
        parsed = _parse_holder(str(existing["holder"]))
        if parsed:
            host, pid = parsed
            if host == hostname and pid == os.getpid():
                # Same process: refresh step only.
                pass
            elif host == hostname:
                if _pid_alive(pid):
                    holder = existing["holder"]
                    other_step = existing.get("step")
                    raise RuntimeError(f"task locked by live process {holder} step={other_step}")
                clear_lock(task_root, state)
            else:
                raise RuntimeError(
                    f"task locked by another host ({existing['holder']}); "
                    "v0.1.0 does not support lock clear"
                )
        else:
            clear_lock(task_root, state)

    acquired_at = utc_now_iso()
    payload = {"holder": my_holder, "step": step, "acquired_at": acquired_at}
    path = lock_path(task_root)
    tmp = path.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    state["run"]["lock"] = payload


def release_lock(task_root: Path, state: dict[str, Any]) -> None:
    clear_lock(task_root, state)
