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

MODEL="${DFLASH_MODEL:-TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit}"
DRAFT="${DFLASH_DRAFT:-z-lab/Qwen3.6-35B-A3B-DFlash}"
HOST="${DDTREE_HOST:-127.0.0.1}"
PORT="${DDTREE_PORT:-8216}"
TREE_BUDGET="${DDTREE_TREE_BUDGET:-4}"

export PYTHONPATH="$ROOT/bench/ddtree-mlx${PYTHONPATH:+:$PYTHONPATH}"
export DDTREE_DEFAULT_MAX_TOKENS="${DDTREE_DEFAULT_MAX_TOKENS:-4096}"

printf '[%s] Starting DDTree server\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
printf '[%s] Target: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$MODEL"
printf '[%s] Draft:  %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$DRAFT"
printf '[%s] API:    http://%s:%s/v1\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$HOST" "$PORT"
printf '[%s] Budget: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$TREE_BUDGET"

exec "$PY" "$ROOT/bench/ddtree-mlx/ddtree_server.py" \
  --host "$HOST" \
  --port "$PORT" \
  --model "$MODEL" \
  --draft "$DRAFT" \
  --tree-budget "$TREE_BUDGET"

