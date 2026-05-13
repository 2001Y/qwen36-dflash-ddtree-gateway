#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
ROOT_DIR="${SCRIPT_DIR:h}"
cd "$ROOT_DIR"

VENV_PY="${DFLASH_PYTHON:-$ROOT_DIR/.venv/bin/python}"
DFLASH="${DFLASH_BIN:-$ROOT_DIR/.venv/bin/dflash}"

MODEL="${DFLASH_MODEL:-TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit}"
DRAFT="${DFLASH_DRAFT:-z-lab/Qwen3.6-35B-A3B-DFlash}"
HOST="${DFLASH_HOST:-127.0.0.1}"
PORT="${DFLASH_PORT:-8000}"
PROFILE="${DFLASH_PROFILE:-balanced}"
DIAGNOSTICS="${DFLASH_DIAGNOSTICS:-basic}"
MAX_CTX="${DFLASH_MAX_CTX:-24000}"
PREFILL_STEP_SIZE="${DFLASH_PREFILL_STEP_SIZE:-4096}"
PREFIX_CACHE_MAX_ENTRIES="${DFLASH_PREFIX_CACHE_MAX_ENTRIES:-4}"
PREFIX_CACHE_MAX_BYTES="${DFLASH_PREFIX_CACHE_MAX_BYTES:-8589934592}"
PREFIX_CACHE_L2="${DFLASH_PREFIX_CACHE_L2:-0}"
PREFIX_CACHE_L2_DIR="${DFLASH_PREFIX_CACHE_L2_DIR:-$ROOT_DIR/.artifacts/dflash/prefix-l2}"
PREFIX_CACHE_L2_MAX_BYTES="${DFLASH_PREFIX_CACHE_L2_MAX_BYTES:-53687091200}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

if [[ ! -x "$VENV_PY" ]]; then
  log "ERROR: Python venv not found: $VENV_PY"
  log "Run setup first: UV_CACHE_DIR=.uv-cache uv venv .venv --python /opt/homebrew/Cellar/python@3.12/3.12.13/bin/python3.12"
  exit 1
fi

if [[ ! -x "$DFLASH" ]]; then
  log "ERROR: dflash CLI not found: $DFLASH"
  log "Run setup first: UV_CACHE_DIR=.uv-cache uv pip install -U git+https://github.com/bstnxbt/dflash-mlx huggingface_hub"
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  log "Quick launch file is structurally ready."
  log "Python: $VENV_PY"
  log "DFlash: $DFLASH"
  log "Target: $MODEL"
  log "Draft:  $DRAFT"
  log "API:    http://$HOST:$PORT/v1"
  log "Max ctx: $MAX_CTX"
  log "Profile: $PROFILE"
  log "Prefill step: $PREFILL_STEP_SIZE"
  log "Prefix L1: entries=$PREFIX_CACHE_MAX_ENTRIES bytes=$PREFIX_CACHE_MAX_BYTES"
  log "Prefix L2: $PREFIX_CACHE_L2"
  exit 0
fi

log "Starting DFlash server"
log "Target: $MODEL"
log "Draft:  $DRAFT"
log "API:    http://$HOST:$PORT/v1"
log "Max ctx: $MAX_CTX"
log "Profile: $PROFILE"
log "Prefill step: $PREFILL_STEP_SIZE"
log "Prefix L1: entries=$PREFIX_CACHE_MAX_ENTRIES bytes=$PREFIX_CACHE_MAX_BYTES"
log "Prefix L2: $PREFIX_CACHE_L2"
log "Ready:  curl http://$HOST:$PORT/v1/models"
log "Note:   first launch downloads and loads the models before the API starts listening"
log "Stop:   press Ctrl-C in this Terminal window"

ARGS=(
  serve
  --model "$MODEL"
  --draft "$DRAFT"
  --host "$HOST"
  --port "$PORT"
  --profile "$PROFILE"
  --diagnostics "$DIAGNOSTICS"
  --dflash-max-ctx "$MAX_CTX"
  --prefill-step-size "$PREFILL_STEP_SIZE"
  --prefix-cache-max-entries "$PREFIX_CACHE_MAX_ENTRIES"
  --prefix-cache-max-bytes "$PREFIX_CACHE_MAX_BYTES"
  --fastpath-max-tokens 0
)

if [[ "$PREFIX_CACHE_L2" == "1" || "$PREFIX_CACHE_L2" == "true" || "$PREFIX_CACHE_L2" == "yes" ]]; then
  ARGS+=(
    --prefix-cache-l2
    --prefix-cache-l2-dir "$PREFIX_CACHE_L2_DIR"
    --prefix-cache-l2-max-bytes "$PREFIX_CACHE_L2_MAX_BYTES"
  )
fi

exec "$DFLASH" "${ARGS[@]}"
