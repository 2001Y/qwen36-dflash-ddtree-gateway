#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it with: brew install uv" >&2
  exit 1
fi

uv venv .venv --python "${PYTHON:-python3.12}"
source .venv/bin/activate
uv pip install -U pip
uv pip install -U "git+https://github.com/bstnxbt/dflash-mlx" huggingface_hub fastapi uvicorn mlx-vlm
uv pip install -e bench/ddtree-mlx

echo "Setup complete."
echo "Next: cp .env.example .env"
echo "Then: hf auth login"
