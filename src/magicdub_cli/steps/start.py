"""start — create task, copy video, write skeleton state."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from magicdub_cli import constants as C
from magicdub_cli.config import load_config
from magicdub_cli.errors import INPUT_INVALID, StepResult, fail_result, ok_result
from magicdub_cli.media.files import file_ref
from magicdub_cli.state.io import new_state, new_task_id, save_state
from magicdub_cli.taskdir import create_task_dir


def run_start(
    *, video: str, src_lang: str, tgt_lang: str
) -> tuple[Path, dict[str, Any], StepResult]:
    video_path = Path(video).expanduser().resolve()
    if not video_path.is_file():
        return Path(), {}, fail_result(INPUT_INVALID, f"video not found: {video}")
    if not src_lang or not tgt_lang:
        return Path(), {}, fail_result(INPUT_INVALID, "src and tgt languages are required")

    config = load_config()
    task_root, title = create_task_dir(config["projects_dir"], video_path)
    ext = video_path.suffix.lstrip(".") or "mp4"
    dest = task_root / C.MEDIA_SRC / f"video.{ext}"
    shutil.copy2(video_path, dest)

    slots = {name: {"order": list(order)} for name, order in config["slots"].items()}
    state = new_state(
        task_id=new_task_id(),
        title=title,
        src_language=src_lang,
        tgt_language=tgt_lang,
        fitting=dict(config["fitting"]),
        slots=slots,
    )
    state["assets"]["src"]["video"] = file_ref(dest, relative_to=task_root)
    state["run"]["status"] = "running"
    state["run"]["steps"]["start"]["status"] = "done"
    save_state(task_root, state)
    return task_root, state, ok_result()
