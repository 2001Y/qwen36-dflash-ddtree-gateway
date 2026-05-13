#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"

MODEL_ENV="$SCRIPT_DIR/.dflash-backend.env"
if [[ -f "$MODEL_ENV" ]]; then
  source "$MODEL_ENV"
fi

export DFLASH_HOST="${DFLASH_HOST:-127.0.0.1}"
export DFLASH_PORT="${DFLASH_PORT:-8001}"

exec "$SCRIPT_DIR/start-dflash.command" "$@"
