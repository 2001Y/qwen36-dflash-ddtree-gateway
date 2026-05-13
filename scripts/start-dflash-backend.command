#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"

REQUESTED_DFLASH_MODEL="${DFLASH_MODEL:-}"
REQUESTED_DFLASH_DRAFT="${DFLASH_DRAFT:-}"

ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi

MODEL_ENV="$ROOT_DIR/.dflash-backend.env"
if [[ -f "$MODEL_ENV" ]]; then
  source "$MODEL_ENV"
fi

if [[ -n "$REQUESTED_DFLASH_MODEL" ]]; then
  export DFLASH_MODEL="$REQUESTED_DFLASH_MODEL"
fi

if [[ -n "$REQUESTED_DFLASH_DRAFT" ]]; then
  export DFLASH_DRAFT="$REQUESTED_DFLASH_DRAFT"
fi

export DFLASH_HOST="${DFLASH_HOST:-127.0.0.1}"
export DFLASH_PORT="${DFLASH_PORT:-8001}"

exec "$SCRIPT_DIR/start-dflash.command" "$@"
