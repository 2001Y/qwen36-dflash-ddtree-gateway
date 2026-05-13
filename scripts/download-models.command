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

MODELS_DIR="${DFLASH_MODELS_DIR:-$ROOT_DIR/.models}"
if [[ "$MODELS_DIR" != /* ]]; then
  MODELS_DIR="$ROOT_DIR/$MODELS_DIR"
fi

HF_CLI="${HF_CLI:-$ROOT_DIR/.venv/bin/huggingface-cli}"
if [[ ! -x "$HF_CLI" ]]; then
  printf '[%s] ERROR: huggingface-cli not found: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$HF_CLI" >&2
  exit 1
fi

export HF_HOME="${HF_HOME:-$MODELS_DIR/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
unset HF_HUB_OFFLINE
unset TRANSFORMERS_OFFLINE

MODELS=(
  "${DFLASH_MODEL:-TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit}"
  "${DFLASH_DRAFT:-z-lab/Qwen3.6-35B-A3B-DFlash}"
  "Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit"
)

printf '[%s] Hugging Face cache: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$HF_HUB_CACHE"
for model in "${MODELS[@]}"; do
  printf '[%s] Download/check: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$model"
  "$HF_CLI" download "$model"
done

printf '[%s] Done.\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
