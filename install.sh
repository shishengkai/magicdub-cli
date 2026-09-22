#!/usr/bin/env bash
# Install / upgrade / rescue magicdub-cli for the current user.
#
# First install, upgrade when the `magicdub` command is missing/broken, or refresh deps:
#   curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/install.sh | sh
#   sh install.sh
#
# Day-to-day upgrade when `magicdub` already works:
#   magicdub update
#
# Version selection (install + update):
#   default → latest *published, non-prerelease* GitHub Release tag
#   override → MAGICDUB_REF=v0.1.1|main|<sha>
#   MAGICDUB_REPO_URL=…  — git URL override (slug inferred for the API)
#
set -euo pipefail

REPO_URL="${MAGICDUB_REPO_URL:-https://github.com/shishengkai/magicdub-cli.git}"
REPO_SLUG="${MAGICDUB_REPO_SLUG:-shishengkai/magicdub-cli}"

say() { printf '%s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

need_unix() {
  case "$(uname -s)" in
    Darwin | Linux) ;;
    *)
      err "this installer supports macOS and Linux only; on Windows install uv + ffmpeg, then use: uv tool install --force git+${REPO_URL}@<release-tag>"
      exit 1
      ;;
  esac
}

ensure_path() {
  export PATH="${HOME}/.local/bin:${PATH}"
  if [ -d "${HOME}/.cargo/bin" ]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
  fi
}

resolve_ref() {
  if [ -n "${MAGICDUB_REF:-}" ]; then
    printf '%s\n' "${MAGICDUB_REF}"
    return
  fi
  if ! have curl; then
    err "curl is required to resolve the latest GitHub Release (or set MAGICDUB_REF)"
    exit 1
  fi
  if ! have python3; then
    err "python3 is required to parse the latest GitHub Release (or set MAGICDUB_REF)"
    exit 1
  fi
  local api="https://api.github.com/repos/${REPO_SLUG}/releases/latest"
  local json tag
  if ! json="$(curl -fsSL \
    -H 'Accept: application/vnd.github+json' \
    -H 'User-Agent: magicdub-cli-install' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "${api}")"; then
    err "failed to fetch ${api}; publish a Release or set MAGICDUB_REF"
    exit 1
  fi
  tag="$(RELEASE_JSON="${json}" python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["RELEASE_JSON"])
if data.get("draft") or data.get("prerelease"):
    sys.stderr.write("latest release is draft/prerelease; refusing\n")
    sys.exit(2)
tag = (data.get("tag_name") or "").strip()
if not tag:
    sys.stderr.write("latest release has empty tag_name\n")
    sys.exit(2)
print(tag)
PY
)" || {
    err "could not parse latest release tag; set MAGICDUB_REF explicitly"
    exit 1
  }
  printf '%s\n' "${tag}"
}

install_uv() {
  if have uv; then
    say "uv: $(uv --version)"
    return
  fi
  say "uv not found; installing via https://astral.sh/uv"
  if ! have curl; then
    err "curl is required to install uv"
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ensure_path
  if ! have uv; then
    err "uv installed but not on PATH; open a new shell or add ~/.local/bin to PATH"
    exit 1
  fi
  say "uv: $(uv --version)"
}

ensure_ffmpeg() {
  if have ffmpeg && have ffprobe; then
    say "ffmpeg: $(ffmpeg -version 2>/dev/null | head -n 1)"
    return
  fi

  say "ffmpeg/ffprobe missing; trying to install…"
  if have brew; then
    brew install ffmpeg
  elif have apt-get; then
    if have sudo; then
      sudo apt-get update -y
      sudo apt-get install -y ffmpeg
    else
      err "need ffmpeg/ffprobe; run: apt-get update && apt-get install -y ffmpeg"
      exit 1
    fi
  elif have dnf; then
    if have sudo; then
      sudo dnf install -y ffmpeg
    else
      err "need ffmpeg/ffprobe; install ffmpeg with your package manager"
      exit 1
    fi
  else
    err "need ffmpeg and ffprobe on PATH; install them with your OS package manager, then re-run"
    exit 1
  fi

  if ! have ffmpeg || ! have ffprobe; then
    err "ffmpeg/ffprobe still missing after install attempt"
    exit 1
  fi
  say "ffmpeg: $(ffmpeg -version 2>/dev/null | head -n 1)"
}

install_magicdub() {
  local ref spec
  ref="$(resolve_ref)"
  spec="git+${REPO_URL}@${ref}"
  say "installing/upgrading magicdub-cli from ${spec}"
  uv tool install --force "${spec}"
  ensure_path
  if ! have magicdub; then
    err "`magicdub` not on PATH; add ~/.local/bin to PATH and retry: magicdub --version"
    exit 1
  fi
  say "installed: $(magicdub --version)"
  # magicdub --version already ensures ~/.magicdub/cli defaults exist
}

main() {
  need_unix
  ensure_path
  install_uv
  ensure_ffmpeg
  install_magicdub
  say ""
  say "done. config: ~/.magicdub/cli/config.yaml"
  say "       credentials: ~/.magicdub/cli/credentials  (fill FAL_KEY / DEEPSEEK_API_KEY)"
  say "next: magicdub run <video> --src en --tgt zh-Hans"
  say "later upgrades: magicdub update   (or re-run this install.sh)"
}

main "$@"
