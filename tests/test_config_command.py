"""Tests for interactive config helpers (slots-only YAML update, registry by slot)."""

from __future__ import annotations

from pathlib import Path

import yaml

from magicdub_cli.adapters.registry import adapter_ids_for_slot, known_adapter_ids
from magicdub_cli.config import load_config, update_slots_in_config_file
from magicdub_cli.configure import _is_interactive_tty, run_config


def test_adapter_ids_for_slot_covers_registry() -> None:
    by_slot = {
        "sep": adapter_ids_for_slot("sep"),
        "asr": adapter_ids_for_slot("asr"),
        "translation": adapter_ids_for_slot("translation"),
        "tts": adapter_ids_for_slot("tts"),
    }
    flat = sorted(aid for ids in by_slot.values() for aid in ids)
    assert flat == known_adapter_ids()
    assert "fal/demucs" in by_slot["sep"]
    assert "fal/whisper" in by_slot["asr"]
    assert "deepseek/deepseek-flash" in by_slot["translation"]
    assert "fal/index-tts-2" in by_slot["tts"]
    assert "fishaudio/s2.1-pro" in by_slot["tts"]
    assert "openrouter/fish-audio/s2.1-pro-free" in by_slot["tts"]


def test_update_slots_preserves_comments_and_other_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "# keep me\n"
        "projects_dir: /tmp/projects\n"
        "fitting:\n"
        "  lower_ratio: 0.8\n"
        "  upper_ratio: 1.2\n"
        "  max_rewrites: 2\n"
        "concurrency:\n"
        "  sep: 1\n"
        "  asr: 1\n"
        "  translation: 3\n"
        "  tts: 3\n"
        "slots:\n"
        "  sep: [fal/demucs]\n"
        "  asr: [fal/whisper]\n"
        "  translation: [deepseek/deepseek-flash]\n"
        "  tts: [fal/index-tts-2]\n",
        encoding="utf-8",
    )
    update_slots_in_config_file(
        {
            "sep": ["fal/sam-audio"],
            "asr": ["bailian/fun-asr"],
            "translation": ["deepseek/deepseek-flash"],
            "tts": ["fishaudio/s2.1-pro"],
        },
        path=path,
    )
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# keep me\n")
    assert "projects_dir: /tmp/projects\n" in text
    assert "fitting:" in text
    assert "concurrency:" in text
    data = yaml.safe_load(text)
    assert data["slots"]["sep"] == ["fal/sam-audio"]
    assert data["slots"]["asr"] == ["bailian/fun-asr"]
    assert data["slots"]["tts"] == ["fishaudio/s2.1-pro"]
    assert data["projects_dir"] == "/tmp/projects"
    loaded = load_config(path)
    assert loaded["slots"]["sep"] == ["fal/sam-audio"]


def test_run_config_rejects_non_tty(monkeypatch) -> None:
    monkeypatch.setattr("magicdub_cli.configure._is_interactive_tty", lambda: False)
    assert run_config() == 2
    # sanity: real helper exists
    assert callable(_is_interactive_tty)
