#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-chord-analyzer-omnizart-local}"
PORT="${PORT:-8501}"

cd "$(dirname "$0")"

port_in_use() {
  local p="$1"
  # lsof가 없을 수도 있어 nc도 함께 시도
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && return 0 || return 1
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$p" >/dev/null 2>&1 && return 0 || return 1
  fi
  return 1
}

# 기본 포트가 이미 사용 중이면 다음 포트로 자동 이동
if port_in_use "$PORT"; then
  for p in 8502 8503 8504 8505 8506; do
    if ! port_in_use "$p"; then
      PORT="$p"
      break
    fi
  done
fi

echo "== Build =="
docker build -f Dockerfile.omnizart-local -t "$IMAGE" .

echo
echo "== Run =="
echo "Open: http://localhost:${PORT}"
docker run --rm -p "${PORT}:8501" "$IMAGE"

