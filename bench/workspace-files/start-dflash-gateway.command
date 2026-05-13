#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

PY="$SCRIPT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  printf '[%s] ERROR: Python venv not found: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$PY" >&2
  exit 1
fi

export DFLASH_GATEWAY_HOST="${DFLASH_GATEWAY_HOST:-127.0.0.1}"
export DFLASH_GATEWAY_PORT="${DFLASH_GATEWAY_PORT:-8000}"
export DFLASH_BACKEND_HOST="${DFLASH_BACKEND_HOST:-127.0.0.1}"
export DFLASH_BACKEND_PORT="${DFLASH_BACKEND_PORT:-8001}"
export DFLASH_GATEWAY_BACKEND_COMMAND="${DFLASH_GATEWAY_BACKEND_COMMAND:-$SCRIPT_DIR/start-dflash-backend.command}"

exec "$PY" "$SCRIPT_DIR/dflash_gateway.py" "$@"
