#!/usr/bin/env bash
# Install / upgrade / rescue magicdub (package magicdub-cli) for the current user.
#
# First install, upgrade when magicdub is missing/broken, or refresh deps:
#   sh install.sh
#   curl -fsSL …/install.sh | sh
#
# Day-to-day upgrade when magicdub already works:
#   magicdub update
#
# Optional:
#   MAGICDUB_REF=main|v0.1.0|<sha>  — git ref (default: main)
#   MAGICDUB_REPO_URL=…             — git URL override

set -euo pipefail

REPO_URL="${MAGICDUB_REPO_URL:-https://github.com/shishengkai/magicdub-cli.git}"
REF="${MAGICDUB_REF:-main}"

say() { printf '%s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; }

need_unix() {
  case "$(uname -s)" in
    Darwin | Linux) ;;
    *)
      err "this installer supports macOS and Linux only; on Windows install uv + ffmpeg, then: uv tool install git+${REPO_URL}@${REF}"
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

have() { command -v "$1" >/dev/null 2>&1; }

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
  local spec="git+${REPO_URL}@${REF}"
  say "installing/upgrading magicdub from ${spec}"
  # --force refreshes an existing tool install (upgrade + rescue)
  uv tool install --force "${spec}"
  ensure_path
  if ! have magicdub; then
    err "magicdub not on PATH; add ~/.local/bin to PATH and retry: magicdub --version"
    exit 1
  fi
  say "magicdub: $(magicdub --version)"
}

main() {
  need_unix
  ensure_path
  install_uv
  ensure_ffmpeg
  install_magicdub
  say ""
  say "done. next:"
  say "  1. put keys in ~/.magicdub/cli/credentials  (FAL_KEY, DEEPSEEK_API_KEY)"
  say "  2. magicdub run <video> --src en --tgt zh-Hans"
  say "  3. later upgrades: magicdub update   (or re-run this install.sh)"
}

main "$@"
