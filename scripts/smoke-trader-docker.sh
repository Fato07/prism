#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    ROOT="$git_root"
  else
    ROOT="$(pwd)"
  fi
fi
ROOT="$(cd "$ROOT" && pwd)"

IMAGE="${IMAGE:-prism-trader-smoke:${GITHUB_SHA:-local}}"
CONTAINER="prism-trader-smoke-${RANDOM}-$$"
LOG_FILE="$(mktemp)"
HEALTH_FILE="$(mktemp)"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -f "$LOG_FILE" "$HEALTH_FILE"
}
trap cleanup EXIT

echo "Building $IMAGE from $ROOT/apps/trader/Dockerfile"
docker build -f "$ROOT/apps/trader/Dockerfile" -t "$IMAGE" "$ROOT"

echo "Starting $CONTAINER"
docker run -d --name "$CONTAINER" \
  -e DATABASE_URL="postgresql://prism:prism@127.0.0.1:1/prism?connect_timeout=1" \
  -e CIRCLE_API_KEY="dummy-circle-api-key" \
  -e CIRCLE_ENTITY_SECRET="dummy-circle-entity-secret" \
  -e CIRCLE_WALLET_SET_ID="dummy-wallet-set" \
  -e PINATA_JWT="dummy-pinata-jwt" \
  -e ARC_RPC_URL="http://127.0.0.1:8545" \
  -e ANTHROPIC_API_KEY="dummy-anthropic-api-key" \
  -e CIRCLE_WALLET_TRADER_ID="dummy-trader-wallet" \
  -e CIRCLE_WALLET_TRADER_ADDRESS="0x0000000000000000000000000000000000000001" \
  -e TRADER_MODEL="claude-sonnet-4-20250514" \
  -e LOCALE="EE" \
  -e PRISM_TRADE_MODE="paper" \
  -p 127.0.0.1::3201 \
  "$IMAGE" >/dev/null

for _ in {1..40}; do
  docker logs "$CONTAINER" >"$LOG_FILE" 2>&1 || true

  if grep -Fq 'workspace in `tool.uv.sources`' "$LOG_FILE" \
    || grep -Fq 'Failed to parse entry: `prism-sentinel`' "$LOG_FILE"; then
    echo "::error::Trader container hit the uv workspace parsing failure."
    cat "$LOG_FILE"
    exit 1
  fi

  port="$(docker port "$CONTAINER" 3201/tcp 2>/dev/null | awk -F: '/127[.]0[.]0[.]1/ {print $NF; exit}')"
  if [[ -n "$port" ]] && curl -fsS "http://127.0.0.1:$port/health" >"$HEALTH_FILE" 2>/dev/null; then
    echo "Trader Docker smoke passed: $(cat "$HEALTH_FILE")"
    exit 0
  fi

  if ! docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
    echo "::error::Trader container exited before /health became available."
    cat "$LOG_FILE"
    exit 1
  fi

  sleep 1
done

echo "::error::Timed out waiting for trader /health."
cat "$LOG_FILE"
exit 1
