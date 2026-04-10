#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  echo "Docker Compose not found. Install docker-compose or docker compose." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is not installed." >&2
  exit 1
fi

echo "==> Updating repository"
git pull --ff-only

echo "==> Rebuilding containers"
"${COMPOSE_CMD[@]}" up -d --build

echo "==> Waiting for API healthcheck"
ATTEMPTS=20
SLEEP_SECONDS=3
HEALTH_URL="${HEALTH_URL:-http://localhost:8080/health}"

for ((i=1; i<=ATTEMPTS; i++)); do
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    echo "Healthcheck passed: $HEALTH_URL"
    echo "==> Container status"
    "${COMPOSE_CMD[@]}" ps
    exit 0
  fi

  echo "Attempt $i/$ATTEMPTS: API is not ready yet"
  sleep "$SLEEP_SECONDS"
done

echo "Healthcheck failed: $HEALTH_URL" >&2
echo "==> Last API logs"
"${COMPOSE_CMD[@]}" logs --tail=80 api >&2
exit 1
