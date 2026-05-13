#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/2001y/Documents/Codex/2026-05-10/mlx-omlx-dflash-mlx-z-lab"
cd "$ROOT"

STAMP="$(date '+%Y%m%d-%H%M%S')-youssofal-top25-continuation"
OUT_DIR="$ROOT/.artifacts/dflash/ts-bench-matrix/$STAMP"
mkdir -p "$OUT_DIR"
RUNNER_LOG="$OUT_DIR/runner.log"

export BENCHMARK_ENGINE_MATRIX_FILE="$ROOT/benchmark-engine-matrix-local.py"
export PYTHONDONTWRITEBYTECODE=1
export DFLASH_PROFILE="${DFLASH_PROFILE:-balanced}"
export DFLASH_MAX_CTX="${DFLASH_MAX_CTX:-24000}"
export DFLASH_PREFILL_STEP_SIZE="${DFLASH_PREFILL_STEP_SIZE:-4096}"
export DFLASH_PREFIX_CACHE_MAX_ENTRIES="${DFLASH_PREFIX_CACHE_MAX_ENTRIES:-4}"
export DFLASH_PREFIX_CACHE_MAX_BYTES="${DFLASH_PREFIX_CACHE_MAX_BYTES:-8GB}"
export DFLASH_PREFIX_CACHE_L2="${DFLASH_PREFIX_CACHE_L2:-0}"

{
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting Youssofal TOP_25 continuation"
  echo "OUT_DIR=$OUT_DIR"
  echo "BENCHMARK_ENGINE_MATRIX_FILE=$BENCHMARK_ENGINE_MATRIX_FILE"
} >> "$RUNNER_LOG"

set +e
"$ROOT/.venv/bin/python" "$ROOT/benchmark-ts-bench-matrix.py" \
  --engines dflash,ddtree \
  --candidates qwen36_35b_a3b_youssofal \
  --cached-only \
  --exercise top25 \
  --exercise-mode per-exercise \
  --agent aider \
  --tree-budget 4 \
  --gateway-port 8300 \
  --backend-port 8301 \
  --ddtree-port 8316 \
  --start-timeout 1800 \
  --preflight-timeout 1800 \
  --request-timeout 3600 \
  --ts-bench-timeout 900 \
  --outer-timeout 1200 \
  --min-system-free-percent 20 \
  --out-dir "$OUT_DIR" >> "$RUNNER_LOG" 2>&1

status=$?
set -e
echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] finished status=$status" >> "$RUNNER_LOG"
exit "$status"
