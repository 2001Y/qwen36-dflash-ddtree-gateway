#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/2001y/Documents/Codex/2026-05-10/mlx-omlx-dflash-mlx-z-lab"
cd "$ROOT"

STAMP="$(date '+%Y%m%d-%H%M%S')-youssofal-ddtree-top25-continuation"
OUT_DIR="$ROOT/.artifacts/dflash/ts-bench-matrix/$STAMP"
mkdir -p "$OUT_DIR"
RUNNER_LOG="$OUT_DIR/runner.log"

export BENCHMARK_ENGINE_MATRIX_FILE="$ROOT/benchmark-engine-matrix-local.py"
export PYTHONDONTWRITEBYTECODE=1
export BENCH_PYTHON="${BENCH_PYTHON:-/private/tmp/mlx-dflash-bench-venv/bin/python}"
export BENCH_VENV_BIN="${BENCH_VENV_BIN:-$(dirname "$BENCH_PYTHON")}"

{
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting Youssofal DDTree TOP_25 continuation"
  echo "OUT_DIR=$OUT_DIR"
  echo "BENCHMARK_ENGINE_MATRIX_FILE=$BENCHMARK_ENGINE_MATRIX_FILE"
  echo "BENCH_PYTHON=$BENCH_PYTHON"
  echo "BENCH_VENV_BIN=$BENCH_VENV_BIN"
} >> "$RUNNER_LOG"

set +e
"$BENCH_PYTHON" "$ROOT/benchmark-ts-bench-matrix.py" \
  --engines ddtree \
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
printf '%s\n' "$OUT_DIR" >> "$RUNNER_LOG"
printf '%s\n' "$OUT_DIR"
exit "$status"
