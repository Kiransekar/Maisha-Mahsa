#!/usr/bin/env bash
# Encrypted backup of the Maisha-Mahsa data volume (SQLite DB + document store) via restic.
# (LAUNCH_READINESS P6-BACKUP.) Run from cron; see infra/backup/restic.cron.
#
# Required env:
#   RESTIC_REPOSITORY   e.g. s3:s3.amazonaws.com/my-bucket/maisha  or  /srv/restic
#   RESTIC_PASSWORD     repository encryption password (keep it OUT of the repo)
# Optional:
#   MAISHA_DATA_DIR     host path of the data volume (default /var/lib/docker/volumes/maisha_data/_data)
#   RESTIC_KEEP_DAILY / RESTIC_KEEP_WEEKLY / RESTIC_KEEP_MONTHLY  retention (defaults 7/4/6)
set -euo pipefail

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD:?set RESTIC_PASSWORD}"
DATA_DIR="${MAISHA_DATA_DIR:-/var/lib/docker/volumes/maisha_data/_data}"

# Initialise the repo on first run (idempotent — ignore "already initialized").
restic snapshots >/dev/null 2>&1 || restic init

# A consistent SQLite snapshot: use the online backup API into a temp file, then back THAT up.
SQLITE_DB="${DATA_DIR}/maisha.db"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
if [ -f "${SQLITE_DB}" ]; then
  sqlite3 "${SQLITE_DB}" ".backup '${STAGE}/maisha.db'"
fi

restic backup --tag maisha --host maisha-mahsa "${STAGE}" "${DATA_DIR}" \
  --exclude "${SQLITE_DB}"   # the live DB is captured via the consistent .backup copy

restic forget --prune \
  --keep-daily   "${RESTIC_KEEP_DAILY:-7}" \
  --keep-weekly  "${RESTIC_KEEP_WEEKLY:-4}" \
  --keep-monthly "${RESTIC_KEEP_MONTHLY:-6}"

restic check   # verify repository integrity after every backup
echo "backup complete: $(date -u +%FT%TZ)"
