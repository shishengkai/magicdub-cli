#!/usr/bin/env bash
# Uninstall the magicdub tool (package magicdub-cli).
# Usage:
#   sh uninstall.sh                         # 1) tool + entrypoints only
#   sh uninstall.sh --purge                 # 2) + ~/.magicdub/cli
#   sh uninstall.sh --purge --purge-tasks   # 3) + default task dirs
#   MAGICDUB_PURGE=1 sh uninstall.sh        # same as --purge
#
# --purge-tasks implies --purge (config/credentials go too).

set -euo pipefail

PURGE_CONFIG=0
PURGE_TASKS=0

say() { printf '%s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<'EOF'
Uninstall magicdub (uv tool package: magicdub-cli).

  sh uninstall.sh                       (1) remove tool + entrypoints
  sh uninstall.sh --purge               (2) also delete ~/.magicdub/cli
  sh uninstall.sh --purge --purge-tasks (3) also delete default task dirs
                                        (Movies|Videos/MagicDub/cli)

--purge-tasks implies --purge. Environment MAGICDUB_PURGE=1 equals --purge.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h | --help)
      usage
      exit 0
      ;;
    --purge)
      PURGE_CONFIG=1
      ;;
    --purge-tasks)
      PURGE_TASKS=1
      ;;
    *)
      err "unknown option: $arg"
      usage >&2
      exit 1
      ;;
  esac
done

if [ "${MAGICDUB_PURGE:-0}" = "1" ]; then
  PURGE_CONFIG=1
fi

ensure_path() {
  export PATH="${HOME}/.local/bin:${PATH}"
  if [ -d "${HOME}/.cargo/bin" ]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
  fi
}

remove_shim() {
  local name="$1"
  local path="${HOME}/.local/bin/${name}"
  if [ -e "$path" ] || [ -L "$path" ]; then
    rm -f "$path"
    say "removed ${path}"
  fi
}

uninstall_tool() {
  ensure_path
  if have uv; then
    if uv tool list 2>/dev/null | grep -q '^magicdub-cli'; then
      say "uv tool uninstall magicdub-cli"
      uv tool uninstall magicdub-cli
    else
      say "uv tool magicdub-cli not listed; skipping uv uninstall"
    fi
  else
    say "uv not found; skipping uv tool uninstall"
  fi
  # Old and new entrypoint names may linger as broken symlinks
  remove_shim magicdub
  remove_shim magicdub-cli
}

purge_config() {
  local dir="${HOME}/.magicdub/cli"
  if [ -e "$dir" ]; then
    say "removing ${dir}"
    rm -rf "$dir"
  else
    say "no ${dir} to remove"
  fi
}

purge_tasks() {
  local candidates=(
    "${HOME}/Movies/MagicDub/cli"
    "${HOME}/Videos/MagicDub/cli"
  )
  local d
  for d in "${candidates[@]}"; do
    if [ -e "$d" ]; then
      say "removing ${d}"
      rm -rf "$d"
    fi
  done
}

main() {
  uninstall_tool
  if [ "$PURGE_CONFIG" = "1" ]; then
    purge_config
  else
    say "kept ~/.magicdub/cli (pass --purge to delete config/credentials)"
  fi
  if [ "$PURGE_TASKS" = "1" ]; then
    purge_tasks
  fi
  say "done."
}

main "$@"
