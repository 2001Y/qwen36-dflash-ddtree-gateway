#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/2001y/Documents/Codex/2026-05-10/mlx-omlx-dflash-mlx-z-lab"
cd "$ROOT"

STAMP="$(date '+%Y%m%d-%H%M%S')-youssofal-ddtree-rest-per-exercise"
OUT_ROOT="$ROOT/.artifacts/dflash/ts-bench-matrix/$STAMP"
mkdir -p "$OUT_ROOT"
RUNNER_LOG="$OUT_ROOT/runner.log"

export BENCHMARK_ENGINE_MATRIX_FILE="$ROOT/benchmark-engine-matrix-local.py"
export PYTHONDONTWRITEBYTECODE=1
export BENCH_PYTHON="${BENCH_PYTHON:-/private/tmp/mlx-dflash-bench-venv/bin/python}"
export BENCH_VENV_BIN="${BENCH_VENV_BIN:-$(dirname "$BENCH_PYTHON")}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/mlx-dflash-bench-uv-cache}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-/private/tmp/mlx-dflash-bench-uv-tools}"
export UV_TOOL_BIN_DIR="${UV_TOOL_BIN_DIR:-/private/tmp/mlx-dflash-bench-uv-bin}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/private/tmp/mlx-dflash-bench-ms-playwright}"

EXERCISES=(
  bank-account
  binary-search
  binary-search-tree
  bowling
  complex-numbers
  connect
  crypto-square
  diamond
  dnd-character
  flatten-array
  food-chain
  house
  pascals-triangle
  rational-numbers
  react
  rectangles
  relative-distance
  robot-name
  spiral-matrix
  transpose
  two-bucket
  variable-length-quantity
  wordy
)

{
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting Youssofal DDTree rest per-exercise"
  echo "OUT_ROOT=$OUT_ROOT"
  echo "BENCHMARK_ENGINE_MATRIX_FILE=$BENCHMARK_ENGINE_MATRIX_FILE"
  echo "BENCH_PYTHON=$BENCH_PYTHON"
  echo "BENCH_VENV_BIN=$BENCH_VENV_BIN"
  echo "UV_CACHE_DIR=$UV_CACHE_DIR"
  echo "UV_TOOL_DIR=$UV_TOOL_DIR"
  echo "UV_TOOL_BIN_DIR=$UV_TOOL_BIN_DIR"
  echo "PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH"
  printf 'EXERCISES=%s\n' "${EXERCISES[*]}"
} >> "$RUNNER_LOG"

overall_status=0
index=0
for exercise in "${EXERCISES[@]}"; do
  index=$((index + 1))
  out_dir="$OUT_ROOT/$index-$exercise"
  mkdir -p "$out_dir"
  {
    echo
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] exercise_start index=$index exercise=$exercise out_dir=$out_dir"
  } >> "$RUNNER_LOG"

  set +e
  "$BENCH_PYTHON" "$ROOT/benchmark-ts-bench-matrix.py" \
    --engines ddtree \
    --candidates qwen36_35b_a3b_youssofal \
    --cached-only \
    --exercise "$exercise" \
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
    --out-dir "$out_dir" >> "$RUNNER_LOG" 2>&1
  status=$?
  set -e

  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] exercise_end index=$index exercise=$exercise status=$status" >> "$RUNNER_LOG"
  if [[ "$status" -ne 0 ]]; then
    overall_status="$status"
  fi
done

echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] finished status=$overall_status" >> "$RUNNER_LOG"
printf '%s\n' "$OUT_ROOT" >> "$RUNNER_LOG"
printf '%s\n' "$OUT_ROOT"
exit "$overall_status"
