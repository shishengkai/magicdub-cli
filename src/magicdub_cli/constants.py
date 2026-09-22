"""Factory defaults and path skeletons. User config overlays; tasks freeze copies."""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = 1
ENGINE = "magicdub-cli"
PROGRAM_NAME = "magicdub-cli"
VERSION = "0.1.2"

CNY_QUANTUM = "0.00000001"

# Fitting band (inclusive) and rewrite budget: attempt max = 1 + max_rewrites
FITTING_LOWER_RATIO = 0.8
FITTING_UPPER_RATIO = 1.2
MAX_REWRITES = 2

# Alignment: aligned duration vs src.audio_duration
ALIGNMENT_TOLERANCE_MS = 1

# IndexTTS short reference pad (this adapter only)
INDEX_TTS_MIN_REF_SEC = 0.5
INDEX_TTS_PAD_TO_SEC = 0.6

# External adapter attempts: first + 2 retries
ADAPTER_MAX_ATTEMPTS = 3

STEM_MAX_LEN = 60

CONFIG_DIR_NAME = ".magicdub"
CLI_CONFIG_SUBDIR = "cli"
CREDENTIALS_FILENAME = "credentials"
CONFIG_FILENAME = "config.yaml"

# Relative paths inside a task root
MEDIA_SRC = "media/src"
MEDIA_SENTENCES = "media/sentences"
EXPORTS = "exports"
TMP = "tmp"
STATE_FILENAME = "state.json"
LOCK_FILENAME = "run.lock"

SLOT_DEFAULTS: dict[str, list[str]] = {
    "sep": ["fal/demucs"],
    "asr": ["fal/whisper"],
    "translation": ["deepseek/deepseek-flash"],
    "tts": ["fal/index-tts-2"],
}

CONCURRENCY_DEFAULTS: dict[str, int] = {
    "sep": 1,
    "asr": 1,
    "translation": 3,
    "tts": 3,
}

# Final mix / export
FINAL_WAV_SAMPLE_RATE = 48000
FINAL_AAC_BITRATE = "320k"


def home_magicdub() -> Path:
    return Path.home() / CONFIG_DIR_NAME


def cli_config_dir() -> Path:
    return home_magicdub() / CLI_CONFIG_SUBDIR


def credentials_path() -> Path:
    """CLI-only credentials; not shared with magicdub-skills."""
    return cli_config_dir() / CREDENTIALS_FILENAME


def default_projects_dir() -> Path:
    """Platform default task parent directory."""
    import platform
    import shutil
    import subprocess

    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Movies" / "MagicDub" / "cli"
    if system == "Windows":
        return Path.home() / "Videos" / "MagicDub" / "cli"
    # Linux / other: prefer xdg-user-dir VIDEOS
    xdg = shutil.which("xdg-user-dir")
    if xdg:
        try:
            out = subprocess.run(
                [xdg, "VIDEOS"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            videos = out.stdout.strip()
            if videos:
                return Path(videos) / "MagicDub" / "cli"
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Videos" / "MagicDub" / "cli"
