"""M1 unit tests: state, media, config, taskdir, lock."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magicdub_cli.config import ConfigError, load_config, sanitize_stem
from magicdub_cli.media.files import commit, file_ref, verify_file_ref
from magicdub_cli.state.io import load_state, new_state, new_task_id, save_state
from magicdub_cli.taskdir import acquire_lock, create_task_dir, release_lock


def test_sanitize_stem() -> None:
    assert sanitize_stem("Steve Jobs!.mp4") == "Steve_Jobs"
    long_stem = sanitize_stem("a" * 80 + ".mp4")
    assert len(long_stem) <= 60


def test_state_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "task"
    root.mkdir()
    state = new_state(
        task_id=new_task_id(),
        title="demo",
        src_language="en",
        tgt_language="zh-Hans",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={
            "sep": {"order": ["fal/demucs"]},
            "asr": {"order": ["fal/whisper"]},
            "translation": {"order": ["deepseek/deepseek-flash"]},
            "tts": {"order": ["fal/index-tts-2"]},
        },
    )
    save_state(root, state)
    loaded = load_state(root)
    assert loaded["engine"] == "magicdub-cli"
    assert loaded["title"] == "demo"
    assert loaded["assets"]["cost"]["total"] == 0.0


def test_file_ref_commit_verify(tmp_path: Path) -> None:
    root = tmp_path / "task"
    tmp = root / "tmp" / "demux"
    final = root / "media" / "src"
    tmp.mkdir(parents=True)
    final.mkdir(parents=True)
    src = tmp / "audio.wav"
    src.write_bytes(b"RIFF....WAVE")
    dest = final / "audio.wav"
    commit(src, dest)
    ref = file_ref(dest, relative_to=root)
    assert ref["path"] == "media/src/audio.wav"
    assert ref["size_bytes"] == 12
    verify_file_ref(root, ref)


def test_empty_slots_list_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("slots:\n  sep: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty list"):
        load_config(cfg)


def test_create_task_and_lock(tmp_path: Path) -> None:
    video = tmp_path / "hello world.mp4"
    video.write_bytes(b"x")
    root, title = create_task_dir(tmp_path / "cli", video)
    assert title == "hello_world"
    assert (root / "media" / "src").is_dir()
    state = new_state(
        task_id=new_task_id(),
        title=title,
        src_language="en",
        tgt_language="zh-Hans",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={"sep": {"order": ["fal/demucs"]}, "asr": {"order": ["fal/whisper"]},
               "translation": {"order": ["deepseek/deepseek-flash"]},
               "tts": {"order": ["fal/index-tts-2"]}},
    )
    acquire_lock(root, state, "demux")
    lock = json.loads((root / "run.lock").read_text(encoding="utf-8"))
    assert lock["step"] == "demux"
    assert state["run"]["lock"]["holder"] == lock["holder"]
    # Same process may refresh the step without error.
    acquire_lock(root, state, "sep")
    lock2 = json.loads((root / "run.lock").read_text(encoding="utf-8"))
    assert lock2["step"] == "sep"
    release_lock(root, state)
    assert not (root / "run.lock").exists()
