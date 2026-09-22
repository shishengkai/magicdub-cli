"""Reinstall this tool via ``uv tool install --force`` (self-update)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_REPO_URL = "https://github.com/shishengkai/magicdub-cli.git"
DEFAULT_REPO_SLUG = "shishengkai/magicdub-cli"
_GITHUB_REPO_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)(?P<slug>[^/]+/[^/]+?)(?:\.git)?$"
)


class UpdateError(RuntimeError):
    """Failed to resolve or install an update."""


def repo_slug_from_url(repo_url: str) -> str:
    raw = repo_url.strip()
    m = _GITHUB_REPO_RE.match(raw)
    if m:
        return m.group("slug")
    parsed = urlparse(raw)
    if parsed.netloc == "github.com" and parsed.path:
        parts = parsed.path.strip("/").removesuffix(".git").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return DEFAULT_REPO_SLUG


def fetch_latest_release_tag(repo_slug: str = DEFAULT_REPO_SLUG) -> str:
    """Return the tag of GitHub's latest *published, non-prerelease* release."""
    api = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    req = urllib.request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "magicdub-cli",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                f"no published release found for {repo_slug}; "
                "publish a GitHub Release or pass --ref / MAGICDUB_REF"
            ) from exc
        raise UpdateError(f"GitHub API HTTP {exc.code} for {api}") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"failed to reach GitHub API: {exc}") from exc

    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("latest release is draft/prerelease; refusing to install")
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("latest release has empty tag_name")
    return tag


def resolve_ref(*, ref: str | None = None, repo_url: str | None = None) -> str:
    explicit = (ref or os.environ.get("MAGICDUB_REF") or "").strip()
    if explicit:
        return explicit
    url = (repo_url or os.environ.get("MAGICDUB_REPO_URL") or DEFAULT_REPO_URL).strip()
    return fetch_latest_release_tag(repo_slug_from_url(url))


def resolve_spec(*, ref: str | None = None, repo_url: str | None = None) -> str:
    url = (repo_url or os.environ.get("MAGICDUB_REPO_URL") or DEFAULT_REPO_URL).strip()
    git_ref = resolve_ref(ref=ref, repo_url=url)
    if not url or not git_ref:
        raise ValueError("repo URL and ref must be non-empty")
    return f"git+{url}@{git_ref}"


def run_update(*, ref: str | None = None, repo_url: str | None = None) -> int:
    """Upgrade／重装当前 uv tool。默认跟随最新正式 GitHub Release。"""
    if shutil.which("uv") is None:
        print(
            "error: uv not found on PATH; install uv or re-run install.sh (rescue)",
            file=sys.stderr,
        )
        return 1

    try:
        spec = resolve_spec(ref=ref, repo_url=repo_url)
    except UpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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
