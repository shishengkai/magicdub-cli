"""Deliverable naming and absolute file_ref paths."""

from __future__ import annotations

from pathlib import Path

from magicdub_cli.media.files import file_ref, resolve_asset_path, verify_file_ref
from magicdub_cli.steps.fixed.mixing import deliverable_stem
from magicdub_cli.taskdir import create_task_dir


def test_deliverable_stem_from_input_path() -> None:
    state = {"assets": {"src": {"input_path": "/Movies/clip/foo-bar.mp4"}}, "title": "ignored"}
    assert deliverable_stem(state) == "foo-bar_MagicDub"


def test_deliverable_stem_falls_back_to_title() -> None:
    assert deliverable_stem({"assets": {"src": {}}, "title": "demo"}) == "demo_MagicDub"


def test_file_ref_absolute_outside_task(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    outside = tmp_path / "videos"
    outside.mkdir()
    dest = outside / "clip_MagicDub.mp4"
    dest.write_bytes(b"fake-mp4")
    ref = file_ref(dest, relative_to=task)
    assert Path(ref["path"]).is_absolute()
    assert ref["path"].endswith("clip_MagicDub.mp4")
    assert resolve_asset_path(task, ref) == dest.resolve()
    verify_file_ref(task, ref)


def test_create_task_dir_has_no_exports(tmp_path: Path) -> None:
    video = tmp_path / "src.mp4"
    video.write_bytes(b"x")
    root, _ = create_task_dir(tmp_path / "projects", video)
    assert (root / "media" / "src").is_dir()
    assert (root / "tmp").is_dir()
    assert not (root / "exports").exists()
