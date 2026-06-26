#!/usr/bin/env bash
# Restore the Maisha-Mahsa data volume from a restic snapshot (LAUNCH_READINESS P6-BACKUP).
# Usage:  RESTIC_REPOSITORY=... RESTIC_PASSWORD=... ./restore.sh [SNAPSHOT_ID] [TARGET_DIR]
#   SNAPSHOT_ID  restic snapshot to restore (default: latest)
#   TARGET_DIR   where to restore (default: ./restore-out — NEVER the live volume directly)
set -euo pipefail

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD:?set RESTIC_PASSWORD}"
SNAPSHOT="${1:-latest}"
TARGET="${2:-./restore-out}"

mkdir -p "${TARGET}"
restic restore "${SNAPSHOT}" --target "${TARGET}"
echo "restored ${SNAPSHOT} -> ${TARGET}"
echo "Inspect the restored maisha.db, then stop the stack and swap it into the data volume."
echo "Verify rows, e.g.:  sqlite3 \$(find '${TARGET}' -name maisha.db) 'SELECT count(*) FROM audit_log;'"
