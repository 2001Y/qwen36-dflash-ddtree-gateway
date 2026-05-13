#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/v1}"
MODEL="${DFLASH_MODEL:-TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit}"

curl -s "$BASE_URL/models"
printf '\n'
curl -s "$BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Return exactly OK\"}],
    \"max_tokens\": 8,
    \"temperature\": 0
  }"
printf '\n'

