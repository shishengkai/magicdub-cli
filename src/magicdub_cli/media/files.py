"""File references: sha256 + size_bytes; commit tmp → formal path."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_asset_path(task_root: Path, ref: dict[str, Any]) -> Path:
    """Resolve a file_ref path (task-relative or absolute deliverable)."""
    raw = (ref or {}).get("path")
    if not raw:
        raise ValueError("missing file ref path")
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return (task_root / path).resolve()


def file_ref(path: Path, *, relative_to: Path) -> dict[str, Any]:
    """Build {path, sha256, size_bytes}.

    Paths under ``relative_to`` are stored as posix-relative; otherwise absolute
    (deliverables next to the user's source video).
    """
    abs_path = path.resolve()
    root = relative_to.resolve()
    try:
        stored = abs_path.relative_to(root).as_posix()
    except ValueError:
        stored = abs_path.as_posix()
    return {
        "path": stored,
        "sha256": sha256_file(abs_path),
        "size_bytes": abs_path.stat().st_size,
    }


def verify_file_ref(task_root: Path, ref: dict[str, Any]) -> None:
    if not ref or not ref.get("path"):
        raise ValueError("missing file ref path")
    path = resolve_asset_path(task_root, ref)
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size != ref.get("size_bytes"):
        raise ValueError(f"size mismatch for {ref['path']}: {size} != {ref['size_bytes']}")
    digest = sha256_file(path)
    if digest != ref.get("sha256"):
        raise ValueError(f"sha256 mismatch for {ref['path']}")


def commit(tmp_path: Path, final_path: Path) -> None:
    """Move tmp → final after ensuring parent exists. Overwrites final if present."""
    if not tmp_path.is_file():
        raise FileNotFoundError(tmp_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if final_path.exists():
        final_path.unlink()
    shutil.move(str(tmp_path), str(final_path))
