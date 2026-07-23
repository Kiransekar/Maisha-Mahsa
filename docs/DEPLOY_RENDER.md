# Deploy the demo to Render (test link, ~one click)

A throwaway, shareable test deployment of Maisha-Mahsa on [Render](https://render.com) — the
whole stack in **one container**: Mahsa (the Rust gatekeeper), the Maisha FastAPI/HTMX app, and a
**dev auth stand-in** so you can actually log in. Defined by [`render.yaml`](../render.yaml).

> **This is a DEMO deploy, not production.** It runs `MAISHA_ENVIRONMENT=development`, mints its
> own tokens (no real Better Auth), and uses **ephemeral SQLite** — the demo tenant is re-seeded
> on every boot and **anything you enter resets when the instance restarts / spins down**. For
> real, persistent, multi-tenant production use `infra/docker-compose.prod.yml` + a real Better
> Auth server (see [`DEPLOYMENT.md`](./DEPLOYMENT.md)).

## What runs

One Render **web service** (`runtime: docker`, `infra/render/Dockerfile`, build context = repo
root). `infra/render/start.sh` boots, in order:

1. `python -m app.dev.seed` — loads the "Acme Innovations" demo tenant (idempotent).
2. **Mahsa** on `127.0.0.1:8088` — every ✓ Verified figure is its recomputation.
3. **JWKS auth stand-in** on `127.0.0.1:8790` — publishes the demo signing key.
4. **Maisha API** on `0.0.0.0:$PORT` — the public app.

Auth: visiting any page redirects to **`/dev-login`**, which mints an `OWNER` JWT for the seeded
demo org, drops it in the `maisha_jwt` cookie, and sends you in. (Verified end-to-end against the
real `app.core.betterauth` verifier — signature, `iss`/`aud`/`exp`, org + role.)

## Deploy steps

1. **Push this repo to GitHub** (branch with `render.yaml` at the root):
   ```bash
   git push origin deploy/render-demo      # or merge to main first
   ```
2. In Render: **New → Blueprint** → connect the GitHub repo → pick the branch → **Apply**.
   Render reads `render.yaml`, builds the image (the Rust build makes the first deploy take a few
   minutes), and starts the service. `MAISHA_SESSION_SECRET` is auto-generated.
3. When it goes live, open the service URL. You'll land on **`/dev-login`** → the dashboard, with
   the demo tenant's real numbers. Check `/audit` (hash-chain), `/d/gst` (a late GSTR-3B with
   engine-computed late fee + interest), `/approvals` (a pending payroll run), `/ask`.

## Health & smoke

- `GET /health` → `{"dependencies": {"db": "ok", "mahsa": "ok"}}` (public route).
- `GET /audit/verify` → `{"intact": true, ...}` after sign-in.

## Notes / knobs

- **Free plan** has no persistent disk (hence ephemeral SQLite) and **spins down after ~15 min
  idle**; the next visit cold-starts (re-seeds, a few seconds). To keep data + stay warm, change
  `plan: free` → `plan: starter` in `render.yaml` and add a `disk:` block mounted at `/data`.
- **Region**: `singapore` (closest to India). If unavailable on your account, change to `oregon`.
- **Turn the demo off / go real**: this whole path is gated behind `MAISHA_DEV_AUTH=1` +
  `MAISHA_ENVIRONMENT=development`. Production ignores the dev auth stand-in entirely.
- The **React SPA** (`frontend/`) is intentionally not deployed here — it needs a CORS change on
  the API to run cross-origin (see `DEPLOYMENT.md §5`). The HTMX surface served by the API is the
  full working test surface today.
