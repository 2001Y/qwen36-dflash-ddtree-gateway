#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT="${SCRIPT_DIR:h}"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  printf '[%s] ERROR: Python venv not found: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$PY" >&2
  printf 'Run: ./scripts/setup-macos.sh\n' >&2
  exit 1
fi

export DFLASH_GATEWAY_HOST="${DFLASH_GATEWAY_HOST:-127.0.0.1}"
export DFLASH_GATEWAY_PORT="${DFLASH_GATEWAY_PORT:-8000}"
export DFLASH_BACKEND_HOST="${DFLASH_BACKEND_HOST:-127.0.0.1}"
export DFLASH_BACKEND_PORT="${DFLASH_BACKEND_PORT:-8001}"
export DFLASH_GATEWAY_BACKEND_COMMAND="${DFLASH_GATEWAY_BACKEND_COMMAND:-$SCRIPT_DIR/start-dflash-backend.command}"
export DFLASH_GATEWAY_BACKEND_CWD="${DFLASH_GATEWAY_BACKEND_CWD:-$ROOT}"

exec "$PY" "$ROOT/dflash_gateway.py" "$@"

