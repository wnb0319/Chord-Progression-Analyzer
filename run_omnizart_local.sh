#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-chord-analyzer-omnizart-local}"
PORT="${PORT:-8501}"

cd "$(dirname "$0")"

echo "== Build =="
docker build -f Dockerfile.omnizart-local -t "$IMAGE" .

echo
echo "== Run =="
echo "Open: http://localhost:${PORT}"
docker run --rm -p "${PORT}:8501" "$IMAGE"

