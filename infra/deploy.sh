#!/usr/bin/env bash
# One-command deploy/upgrade of the Maisha-Mahsa production stack (P7).
# Run from the infra/ directory on the VPS. Requires a populated .env (see ../api/.env.example).
#   ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "ERROR: infra/.env missing — cp ../api/.env.example .env and edit it"; exit 1; }
grep -q '^MAISHA_ENVIRONMENT=production' .env || echo "WARN: MAISHA_ENVIRONMENT is not 'production'"

# WS10.2 — CERT-In posture requires NTP-synchronised clocks (audit-chain and incident
# timestamps are evidence). Containers use the host clock, so the check is host-level.
# Override only for a non-systemd host that syncs time another way: SKIP_NTP_CHECK=1 ./deploy.sh
if [ "${SKIP_NTP_CHECK:-0}" != "1" ]; then
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" != "yes" ]; then
    echo "ERROR: host clock is not NTP-synchronised (CERT-In requirement)."
    echo "  Fix:      sudo timedatectl set-ntp true   (see docs/DEPLOYMENT.md §0)"
    echo "  Override: SKIP_NTP_CHECK=1 ./deploy.sh   (only if time is synced another way)"
    exit 1
  fi
fi

# WS10.2 — 180-day log retention: compose logs to journald; the retention window is host-side.
if [ ! -f /etc/systemd/journald.conf.d/maisha.conf ]; then
  echo "WARN: /etc/systemd/journald.conf.d/maisha.conf missing — 180-day log retention not"
  echo "      configured. Install: sudo install -D -m 0644 host/journald-maisha.conf \\"
  echo "               /etc/systemd/journald.conf.d/maisha.conf && sudo systemctl restart systemd-journald"
fi

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
