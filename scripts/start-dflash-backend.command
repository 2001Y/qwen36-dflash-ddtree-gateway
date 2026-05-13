#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"

REQUESTED_DFLASH_MODEL="${DFLASH_MODEL:-}"
REQUESTED_DFLASH_DRAFT="${DFLASH_DRAFT:-}"

ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if [[ -n "$REQUESTED_DFLASH_MODEL" ]]; then
  export DFLASH_MODEL="$REQUESTED_DFLASH_MODEL"
fi

if [[ -n "$REQUESTED_DFLASH_DRAFT" ]]; then
  export DFLASH_DRAFT="$REQUESTED_DFLASH_DRAFT"
fi

MODELS_DIR="${DFLASH_MODELS_DIR:-$ROOT_DIR/.models}"
if [[ "$MODELS_DIR" != /* ]]; then
  MODELS_DIR="$ROOT_DIR/$MODELS_DIR"
fi

export DFLASH_HOST="${DFLASH_HOST:-127.0.0.1}"
export DFLASH_PORT="${DFLASH_PORT:-8001}"
export DFLASH_MODELS_DIR="$MODELS_DIR"
export HF_HOME="${HF_HOME:-$MODELS_DIR/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

exec "$SCRIPT_DIR/start-dflash.command" "$@"
