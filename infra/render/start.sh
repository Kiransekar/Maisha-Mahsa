#!/bin/sh
# Boot the single-container demo stack: seed → Mahsa → JWKS stand-in → API.
# Render sets $PORT and routes public traffic to it; the internal helpers use fixed loopback ports.
set -e

PORT="${PORT:-8000}"

echo "[start] seeding demo tenant (idempotent — a no-op if already seeded)…"
python -m app.dev.seed || echo "[start] seed reported an issue — continuing (app will still boot)"

echo "[start] launching Mahsa (Rust gatekeeper) on 127.0.0.1:8088…"
MAHSA_ADDR=127.0.0.1:8088 mahsa &

echo "[start] launching JWKS auth stand-in on 127.0.0.1:8790…"
uvicorn app.dev.auth_standin:jwks_app --host 127.0.0.1 --port 8790 &

echo "[start] launching Maisha API on 0.0.0.0:${PORT}…"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
