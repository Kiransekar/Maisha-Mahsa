# Maisha-Mahsa — Operations Runbook

Operational procedures for running Maisha-Mahsa in production. Pair with
[`LAUNCH_READINESS.md`](./LAUNCH_READINESS.md) (sequence) and [`USER_GUIDE.md`](./USER_GUIDE.md).

---

## 1. Services

| Service | What | Port | Health |
|---|---|---|---|
| `api` | Maisha (FastAPI) | 8000 | `GET /health` → `dependencies.{db,mahsa}` |
| `dif` | Mahsa (Rust gatekeeper) | 8088 | `GET /health` |
| `scheduler` | `python -m app.jobs serve` — daily capture/brief/dunning/alerts/audit-verify | — | logs |
| `redis` | reserved (future queue) | 6379 | — |
| `caddy` | TLS reverse proxy | 80/443 | — |

Bring up: `make dev` (local) or `docker compose -f infra/docker-compose.yml up -d` (server).

## 2. First-time production setup

1. Copy `api/.env.example` → `.env`; set **`MAISHA_ENVIRONMENT=production`**, a strong
   `MAISHA_APP_PASSWORD` and `MAISHA_SESSION_SECRET`
   (`python -c "import secrets; print(secrets.token_hex(32))"`), `MAISHA_SECURE_COOKIES=true`,
   real `MAISHA_SMTP_*`, and `MAISHA_COMPANY_GSTIN`. The app **refuses to boot** in production
   with default secrets.
2. Apply schema: `make migrate` (`alembic upgrade head`). Do **not** rely on auto-create in prod.
3. (Optional) `make seed` only on a demo box — never on the real company DB.
4. Start the stack; confirm `GET /health` shows `db: ok`, `mahsa: ok`.

## 2b. Deploy to a VPS (P7)

Production runs `infra/docker-compose.prod.yml` (Caddy TLS in front; api/dif/redis internal-only;
migrations run once before api starts; no MailHog).

```bash
# on the VPS (Docker + compose plugin installed):
git clone <repo> /opt/maisha && cd /opt/maisha/infra
cp ../api/.env.example .env          # then edit: MAISHA_ENVIRONMENT=production, strong
                                     # MAISHA_APP_PASSWORD + MAISHA_SESSION_SECRET, MAISHA_DOMAIN,
                                     # real MAISHA_SMTP_*, MAISHA_COMPANY_GSTIN
./deploy.sh                          # builds, runs migrations, starts the stack, waits for health
```

- **DNS:** point `MAISHA_DOMAIN`'s A/AAAA record at the VPS *before* deploy — Caddy provisions a
  Let's Encrypt cert on first boot and redirects HTTP→HTTPS automatically.
- **Ports:** only 80/443 are published (Caddy). Firewall everything else; api/dif/redis are on
  the internal compose network. Audit with `ss -tlnp` / your cloud firewall.
- **Persistence + reboot:** data is on the `maisha_data` volume; all services are
  `restart: unless-stopped`, so the stack survives reboots.
- **Verify (P7-PRODSMOKE):** `curl -sf https://<domain>/health` (deps ok) and
  `curl -sf https://<domain>/audit/verify`; then log in, enter a small real dataset, drive each
  domain, confirm Mahsa status + audit entries, and confirm the 8pm brief arrives. Record it.

## 3. Scheduled jobs

The `scheduler` service runs daily at `MAISHA_BRIEF_HOUR:MINUTE` (`MAISHA_BRIEF_TZ`, default
20:00 IST): snapshot capture, CFO brief, dunning, statutory alerts, and the audit-chain check.
Run any once by hand: `make capture | make brief | make dunning | make alerts`, or
`python -m app.jobs audit-verify`.

## 4. Backups (restic)

Config: put `RESTIC_REPOSITORY`, `RESTIC_PASSWORD` (and cloud creds) in `/etc/maisha/backup.env`.

- **Scheduled:** install `infra/backup/restic.cron` (daily 02:30). Each run takes a consistent
  SQLite `.backup`, uploads it, prunes to 7 daily / 4 weekly / 6 monthly, and runs `restic check`.
- **Manual backup:** `set -a; . /etc/maisha/backup.env; infra/backup/backup.sh`
- **Keep `RESTIC_PASSWORD` off the server** (a password-manager / secrets store). Without it the
  backups are unrecoverable — that's the point of encryption, and the main footgun.

### Restore drill (do this BEFORE you need it — P6-BACKUP "Done when")

```bash
set -a; . /etc/maisha/backup.env
infra/backup/restore.sh latest ./restore-out
# verify the restored DB has data:
sqlite3 "$(find ./restore-out -name maisha.db)" 'SELECT count(*) FROM audit_log;'
# cut over: stop the stack, swap the restored maisha.db into the maisha_data volume, restart.
docker compose -f infra/docker-compose.yml stop api scheduler
cp "$(find ./restore-out -name maisha.db)" /var/lib/docker/volumes/maisha_data/_data/maisha.db
docker compose -f infra/docker-compose.yml start api scheduler
```

> **Record each drill here** (date, snapshot id, row counts before/after, outcome). A backup is
> not "done" until a restore has actually been performed and logged.

| Date | Snapshot | audit_log rows | Result |
|---|---|---|---|
| _pending first production drill_ | | | |

## 5. Audit-chain integrity

- Endpoint: `GET /audit/verify` → `{intact, entries}`. The dashboard shows a red banner if broken.
- The scheduler runs `audit-verify` daily and logs `AUDIT CHAIN INTEGRITY FAILURE` (error level)
  if a link is broken — alert on that log line.
- If broken: do **not** trust subsequent numbers; restore from the last good backup and
  investigate which entry's hash diverged (compare `prev_hash` chaining in `audit_log`).

## 6. Incident quick-reference

| Symptom | Cause | Action |
|---|---|---|
| Numbers won't finalise | Mahsa down (`/health` → `mahsa: down`) | restart `dif`; the app degrades safely meanwhile |
| App returns 500s | check `maisha.web` logs (stack traces are logged, never shown to users) | fix; redeploy |
| Login impossible | wrong `MAISHA_APP_PASSWORD` / rotated `MAISHA_SESSION_SECRET` (logs everyone out) | reset env, restart |
| Disk filling | restic cache / logs | check retention; `restic prune` |
| Audit banner red | tamper or corruption | §5 |

## 6b. Rotating secrets

- **App password:** change `MAISHA_APP_PASSWORD` in `.env`, `docker compose ... up -d api`.
- **Session secret:** change `MAISHA_SESSION_SECRET` (this logs out every device immediately).
- **SMTP / cloud creds:** update `MAISHA_SMTP_*` / `MAISHA_CLAUDE_API_KEY`, restart `api` +
  `scheduler`. Secrets live only in `.env` (gitignored) and the restic password file — never in VCS.

## 6c. Updating statutory constants (do this every Finance Act / rate change)

Rates and slabs are **data**, not code, so updates are localised:

- **Direct/indirect tax, PF/ESI/PT/LWF, bonus/gratuity:** edit the data tables in
  `api/app/domains/<domain>/{statutory,*_calc}.py` (each carries a "re-verify annually" comment).
- **Mahsa rules:** edit `dif/rules/rules.yaml` and bump its `version`; keep the Python
  `domains/*/rules.py` IDs in sync (the cross-check test enforces the bijection).
- After any change: `make verify` must be green, then note the change in `BUILD_PROGRESS.md`.
  See `skills/indian-fin-rules` for the per-statute matrix.

## 7. Upgrades

1. Pull new images / code. 2. `make migrate` (Alembic forward-only). 3. Restart `api` +
`scheduler`. 4. Confirm `/health` and `/audit/verify`. Roll back = redeploy previous tag +
restore DB if a migration was destructive (migrations are forward-only; take a backup first).
