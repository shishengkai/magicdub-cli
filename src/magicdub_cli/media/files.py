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


def file_ref(path: Path, *, relative_to: Path) -> dict[str, Any]:
    """Build {path, sha256, size_bytes} with path relative to task root using /."""
    abs_path = path.resolve()
    rel = abs_path.relative_to(relative_to.resolve()).as_posix()
    return {
        "path": rel,
        "sha256": sha256_file(abs_path),
        "size_bytes": abs_path.stat().st_size,
    }


def verify_file_ref(task_root: Path, ref: dict[str, Any]) -> None:
    if not ref or not ref.get("path"):
        raise ValueError("missing file ref path")
    path = task_root / ref["path"]
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
