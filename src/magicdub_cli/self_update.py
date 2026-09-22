"""Reinstall this tool via ``uv tool install --force`` (self-update)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

DEFAULT_REPO_URL = "https://github.com/shishengkai/magicdub-cli.git"
DEFAULT_REF = "main"


def resolve_spec(*, ref: str | None = None, repo_url: str | None = None) -> str:
    url = (repo_url or os.environ.get("MAGICDUB_REPO_URL") or DEFAULT_REPO_URL).strip()
    git_ref = (ref or os.environ.get("MAGICDUB_REF") or DEFAULT_REF).strip()
    if not url or not git_ref:
        raise ValueError("repo URL and ref must be non-empty")
    return f"git+{url}@{git_ref}"


def run_update(*, ref: str | None = None, repo_url: str | None = None) -> int:
    """Upgrade／重装当前 uv tool。需要本机已有 ``uv``。"""
    if shutil.which("uv") is None:
        print(
            "error: uv not found on PATH; install uv or re-run install.sh (rescue)",
            file=sys.stderr,
        )
        return 1

    spec = resolve_spec(ref=ref, repo_url=repo_url)
    cmd = ["uv", "tool", "install", "--force", spec]
    print(f"updating magicdub from {spec}", flush=True)
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        print(
            "error: update failed; try install.sh as rescue "
            "(or: uv tool install --force "
            f"{spec})",
            file=sys.stderr,
        )
        return completed.returncode or 1

    # Show whichever binary is on PATH after refresh
    magicdub = shutil.which("magicdub")
    if magicdub:
        ver = subprocess.run(
            [magicdub, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if ver.returncode == 0 and ver.stdout.strip():
            print(ver.stdout.strip(), flush=True)
    print("done.", flush=True)
    return 0
