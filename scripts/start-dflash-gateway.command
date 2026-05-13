#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  printf '[%s] ERROR: Python venv not found: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$PY" >&2
  exit 1
fi

export DFLASH_GATEWAY_WORKSPACE="${DFLASH_GATEWAY_WORKSPACE:-$ROOT_DIR}"
export DFLASH_GATEWAY_HOST="${DFLASH_GATEWAY_HOST:-127.0.0.1}"
export DFLASH_GATEWAY_PORT="${DFLASH_GATEWAY_PORT:-8000}"
export DFLASH_BACKEND_HOST="${DFLASH_BACKEND_HOST:-127.0.0.1}"
export DFLASH_BACKEND_PORT="${DFLASH_BACKEND_PORT:-8001}"
export DFLASH_GATEWAY_BACKEND_COMMAND="${DFLASH_GATEWAY_BACKEND_COMMAND:-$SCRIPT_DIR/start-dflash-backend.command}"

exec "$PY" "$ROOT_DIR/dflash_gateway.py" "$@"
