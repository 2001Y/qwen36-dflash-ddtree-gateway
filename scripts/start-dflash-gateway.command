#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  printf '[%s] ERROR: Python venv not found: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$PY" >&2
  exit 1
fi

MODELS_DIR="${DFLASH_MODELS_DIR:-$ROOT_DIR/.models}"
if [[ "$MODELS_DIR" != /* ]]; then
  MODELS_DIR="$ROOT_DIR/$MODELS_DIR"
fi

export DFLASH_GATEWAY_HOST="${DFLASH_GATEWAY_HOST:-127.0.0.1}"
export DFLASH_GATEWAY_PORT="${DFLASH_GATEWAY_PORT:-8000}"
export DFLASH_GATEWAY_IDLE_SECONDS="${DFLASH_GATEWAY_IDLE_SECONDS:-1800}"
export DFLASH_GATEWAY_WORKSPACE="${DFLASH_GATEWAY_WORKSPACE:-$ROOT_DIR}"
export DFLASH_BACKEND_HOST="${DFLASH_BACKEND_HOST:-127.0.0.1}"
export DFLASH_BACKEND_PORT="${DFLASH_BACKEND_PORT:-8001}"
export DFLASH_MODELS_DIR="$MODELS_DIR"
export HF_HOME="${HF_HOME:-$MODELS_DIR/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

exec "$PY" "$ROOT_DIR/dflash_gateway.py" "$@"
