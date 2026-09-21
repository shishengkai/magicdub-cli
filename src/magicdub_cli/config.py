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


def load_credentials(path: Path | None = None) -> dict[str, str]:
    """Parse KEY=value files; environment variables override.

    Prefers ``~/.magicdub/credentials``; also reads skills layout
    ``credentials.env`` as read-only fallback for missing keys.
    """
    paths: list[Path] = []
    if path is not None:
        paths.append(path)
    else:
        paths.append(C.credentials_path())
        paths.append(C.home_magicdub() / "credentials.env")

    result: dict[str, str] = {}
    for file_path in paths:
        if not file_path.is_file():
            continue
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in result:
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
        env = os.environ.get(key)
        if env is not None and env != "":
            result[key] = env
    return result


def require_credential(creds: dict[str, str], key: str) -> str:
    value = creds.get(key) or os.environ.get(key)
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
