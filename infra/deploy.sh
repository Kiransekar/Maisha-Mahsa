#!/usr/bin/env bash
# One-command deploy/upgrade of the Maisha-Mahsa production stack (P7).
# Run from the infra/ directory on the VPS. Requires a populated .env (see ../api/.env.example).
#   ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "ERROR: infra/.env missing — cp ../api/.env.example .env and edit it"; exit 1; }
grep -q '^MAISHA_ENVIRONMENT=production' .env || echo "WARN: MAISHA_ENVIRONMENT is not 'production'"

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> building images"
$COMPOSE build

echo "==> applying migrations (one-shot)"
$COMPOSE run --rm migrate

echo "==> starting stack"
$COMPOSE up -d

echo "==> waiting for api health"
for _ in $(seq 1 30); do
  if $COMPOSE exec -T api python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" 2>/dev/null; then
    echo "api healthy"; break
  fi
  sleep 2
done

echo "==> deployed. Public URL: https://$(grep '^MAISHA_DOMAIN=' .env | cut -d= -f2)"
echo "    Verify:  curl -sf https://<domain>/health   and   /audit/verify"
