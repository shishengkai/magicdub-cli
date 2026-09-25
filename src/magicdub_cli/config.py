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

_DEFAULT_CREDENTIAL_KEYS: tuple[str, ...] = (
    "FAL_KEY",
    "DEEPSEEK_API_KEY",
    "MVSEP_API_KEY",
)

_DEFAULT_CREDENTIALS = """\
# magicdub-cli credentials (~/.magicdub/cli/credentials)
# KEY=value. File values win over environment variables.
# Fill in at least FAL_KEY and DEEPSEEK_API_KEY for the default v0.1 adapters.
# MVSEP_API_KEY is required when slots.sep includes mvsep/dnr-v3.

FAL_KEY=
DEEPSEEK_API_KEY=
MVSEP_API_KEY=
"""


def _default_config_mapping() -> dict[str, Any]:
    return {
        "projects_dir": None,
        "fitting": {
            "lower_ratio": C.FITTING_LOWER_RATIO,
            "upper_ratio": C.FITTING_UPPER_RATIO,
            "max_rewrites": C.MAX_REWRITES,
        },
        "concurrency": {k: int(v) for k, v in C.CONCURRENCY_DEFAULTS.items()},
        "slots": {k: list(v) for k, v in C.SLOT_DEFAULTS.items()},
    }


def _fill_missing(defaults: Any, current: Any) -> tuple[Any, bool]:
    """Merge ``defaults`` under ``current``; user values win. Return (merged, changed)."""
    if isinstance(defaults, dict):
        if not isinstance(current, dict):
            return current, False
        out = dict(current)
        changed = False
        for key, default_value in defaults.items():
            if key not in out:
                out[key] = default_value
                changed = True
                continue
            filled, sub_changed = _fill_missing(default_value, out[key])
            if sub_changed:
                out[key] = filled
                changed = True
        return out, changed
    return current, False


def _write_config_mapping(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _credential_keys_in_file(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key:
            keys.add(key)
    return keys


def _ensure_config_file(config_path: Path) -> bool:
    """Create or backfill ``config.yaml``. Returns True if created or updated."""
    if not config_path.exists():
        config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
        return True

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ConfigError("config.yaml must be a mapping")
    merged, changed = _fill_missing(_default_config_mapping(), loaded)
    if not changed:
        return False
    assert isinstance(merged, dict)
    _write_config_mapping(config_path, merged)
    return True


def _ensure_credentials_file(cred_path: Path) -> bool:
    """Create or append missing credential keys. Never changes existing values."""
    if not cred_path.exists():
        cred_path.write_text(_DEFAULT_CREDENTIALS, encoding="utf-8")
        try:
            os.chmod(cred_path, 0o600)
        except OSError:
            pass
        return True

    text = cred_path.read_text(encoding="utf-8")
    present = _credential_keys_in_file(text)
    missing = [key for key in _DEFAULT_CREDENTIAL_KEYS if key not in present]
    if not missing:
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    text += "# added by magicdub-cli (new default keys)\n"
    text += "".join(f"{key}=\n" for key in missing)
    cred_path.write_text(text, encoding="utf-8")
    try:
        os.chmod(cred_path, 0o600)
    except OSError:
        pass
    return True


def ensure_user_files() -> list[Path]:
    """Ensure ``~/.magicdub/cli`` defaults exist; backfill missing keys on upgrade.

    - Missing files: write full templates.
    - Existing ``config.yaml``: add missing keys/sections; keep user values.
    - Existing ``credentials``: append missing ``KEY=`` lines; never overwrite values.
    """
    touched: list[Path] = []
    cli_dir = C.cli_config_dir()
    if not cli_dir.is_dir():
        cli_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cli_dir, 0o700)
        except OSError:
            pass
        touched.append(cli_dir)

    config_path = cli_dir / C.CONFIG_FILENAME
    if _ensure_config_file(config_path):
        touched.append(config_path)

    cred_path = C.credentials_path()
    if _ensure_credentials_file(cred_path):
        touched.append(cred_path)

    return touched


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
