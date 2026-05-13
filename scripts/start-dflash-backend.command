#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT="${SCRIPT_DIR:h}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

export DFLASH_HOST="${DFLASH_BACKEND_HOST:-${DFLASH_HOST:-127.0.0.1}}"
export DFLASH_PORT="${DFLASH_BACKEND_PORT:-${DFLASH_PORT:-8001}}"

exec "$SCRIPT_DIR/start-dflash.command" "$@"

