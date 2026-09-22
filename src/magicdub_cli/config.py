"""Load ~/.magicdub/cli/config.yaml and credentials."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from magicdub_cli import constants as C


class ConfigError(ValueError):
    """Invalid user configuration."""


_DEFAULT_CONFIG_YAML = """\
# magicdub-cli user config (~/.magicdub/cli/config.yaml)
# Omitted keys fall back to built-in defaults. Empty slots lists are errors.

projects_dir: null
fitting:
  lower_ratio: 0.8
  upper_ratio: 1.2
  max_rewrites: 2
concurrency:
  sep: 1
  asr: 1
  translation: 3
  tts: 3
slots:
  sep: [fal/demucs]
  asr: [fal/whisper]
  translation: [deepseek/deepseek-flash]
  tts: [fal/index-tts-2]
"""

_DEFAULT_CREDENTIALS = """\
# magicdub-cli credentials (~/.magicdub/cli/credentials)
# KEY=value. File values win over environment variables.
# Fill in at least FAL_KEY and DEEPSEEK_API_KEY for the default v0.1 adapters.

FAL_KEY=
DEEPSEEK_API_KEY=
"""


def ensure_user_files() -> list[Path]:
    """Create ``~/.magicdub/cli`` defaults if missing. Never overwrite existing files."""
    created: list[Path] = []
    cli_dir = C.cli_config_dir()
    if not cli_dir.is_dir():
        cli_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cli_dir, 0o700)
        except OSError:
            pass
        created.append(cli_dir)

    config_path = cli_dir / C.CONFIG_FILENAME
    if not config_path.exists():
        config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
        created.append(config_path)

    cred_path = C.credentials_path()
    if not cred_path.exists():
        cred_path.write_text(_DEFAULT_CREDENTIALS, encoding="utf-8")
        try:
            os.chmod(cred_path, 0o600)
        except OSError:
            pass
        created.append(cred_path)

    return created


def load_credentials(path: Path | None = None) -> dict[str, str]:
    """Parse ``~/.magicdub/cli/credentials``; fill missing keys from the environment.

    File values win. Environment is used only when a key is absent or empty in the file.
    Does not read skills files (``~/.magicdub/credentials`` or ``credentials.env``).
    """
    file_path = path if path is not None else C.credentials_path()
    result: dict[str, str] = {}
    if file_path.is_file():
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value

    for key in (
        "FAL_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "FISH_API_KEY",
        "OPENROUTER_API_KEY",
        "MVSEP_API_KEY",
        *list(result.keys()),
    ):
        if result.get(key):
            continue
        env = os.environ.get(key)
        if env is not None and env != "":
            result[key] = env
    return result


def require_credential(creds: dict[str, str], key: str) -> str:
    value = creds.get(key) or ""
    if not value:
        value = os.environ.get(key) or ""
    if not value:
        raise ConfigError(f"missing credential {key}")
    return value


def _merge_slots(raw: dict[str, Any] | None) -> dict[str, list[str]]:
    slots: dict[str, list[str]] = {}
    raw = raw or {}
    for name, default in C.SLOT_DEFAULTS.items():
        if name not in raw:
            slots[name] = list(default)
            continue
        value = raw[name]
        if value is None:
            slots[name] = list(default)
            continue
        if not isinstance(value, list):
            raise ConfigError(f"slots.{name} must be a list")
        if len(value) == 0:
            raise ConfigError(f"slots.{name} is an empty list; omit the key to use defaults")
        slots[name] = [str(x) for x in value]
    return slots


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Return effective config: file overlays constants; missing keys use defaults."""
    path = path or (C.cli_config_dir() / C.CONFIG_FILENAME)
    raw: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ConfigError("config.yaml must be a mapping")
        raw = loaded

    fitting_raw = raw.get("fitting") or {}
    concurrency_raw = raw.get("concurrency") or {}

    projects_dir = raw.get("projects_dir")
    if projects_dir in (None, "null"):
        projects_path = C.default_projects_dir()
    else:
        projects_path = Path(str(projects_dir)).expanduser()

    fitting = {
        "lower_ratio": float(fitting_raw.get("lower_ratio", C.FITTING_LOWER_RATIO)),
        "upper_ratio": float(fitting_raw.get("upper_ratio", C.FITTING_UPPER_RATIO)),
        "max_rewrites": int(fitting_raw.get("max_rewrites", C.MAX_REWRITES)),
    }
    concurrency = {
        k: int(concurrency_raw.get(k, C.CONCURRENCY_DEFAULTS[k]))
        for k in C.CONCURRENCY_DEFAULTS
    }
    slots = _merge_slots(raw.get("slots"))

    return {
        "projects_dir": projects_path,
        "fitting": fitting,
        "concurrency": concurrency,
        "slots": slots,
    }


_STEM_RE = re.compile(r"[^A-Za-z0-9_-]+")


def sanitize_stem(name: str) -> str:
    stem = Path(name).stem
    stem = _STEM_RE.sub("_", stem).strip("_")
    if not stem:
        stem = "video"
    if len(stem) > C.STEM_MAX_LEN:
        stem = stem[: C.STEM_MAX_LEN].rstrip("_")
    return stem
