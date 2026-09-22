"""M1 unit tests: state, media, config, taskdir, lock."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magicdub_cli.config import ConfigError, load_config, load_credentials, sanitize_stem
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


def test_credentials_file_wins_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred = tmp_path / "credentials"
    cred.write_text("FAL_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("FAL_KEY", "from-env")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-only")
    loaded = load_credentials(cred)
    assert loaded["FAL_KEY"] == "from-file"
    assert loaded["DEEPSEEK_API_KEY"] == "env-only"


def test_ensure_user_files_creates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from magicdub_cli import constants as C
    from magicdub_cli.config import ensure_user_files

    monkeypatch.setattr(C, "home_magicdub", lambda: tmp_path / ".magicdub")
    created = ensure_user_files()
    cfg = tmp_path / ".magicdub" / "cli" / "config.yaml"
    cred = tmp_path / ".magicdub" / "cli" / "credentials"
    assert cfg in created and cred in created
    assert "fal/whisper" in cfg.read_text(encoding="utf-8")
    assert "FAL_KEY=" in cred.read_text(encoding="utf-8")
    cfg.write_text("# user edited\n", encoding="utf-8")
    assert ensure_user_files() == []
    assert cfg.read_text(encoding="utf-8") == "# user edited\n"


def test_update_spec_and_requires_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    from magicdub_cli.self_update import resolve_spec, run_update

    monkeypatch.setattr(
        "magicdub_cli.self_update.fetch_latest_release_tag",
        lambda slug="shishengkai/magicdub-cli": "v9.9.9",
    )
    assert resolve_spec(repo_url="https://github.com/shishengkai/magicdub-cli.git") == (
        "git+https://github.com/shishengkai/magicdub-cli.git@v9.9.9"
    )
    assert resolve_spec(ref="abc", repo_url="https://example.com/r.git") == (
        "git+https://example.com/r.git@abc"
    )
    monkeypatch.setattr("magicdub_cli.self_update.shutil.which", lambda _: None)
    assert run_update() == 1


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
