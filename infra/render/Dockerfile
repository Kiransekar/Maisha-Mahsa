# Single-container Render deploy — Mahsa (Rust gatekeeper) + Maisha (FastAPI/HTMX) + the dev
# auth stand-in, all behind one public port. This exists ONLY for a throwaway demo/test deploy
# (see render.yaml + docs/DEPLOY_RENDER.md); the real production path is infra/docker-compose.prod.yml.
#
# Build context MUST be the repo root — this image needs both dif/ and api/.

# ── stage 1: build the Mahsa binary (mirrors dif/Dockerfile) ──────────────────────────────────────
FROM rust:1-slim AS mahsa-build
WORKDIR /build
COPY dif/Cargo.toml ./
COPY dif/src ./src
COPY dif/rules ./rules
COPY dif/tests ./tests
RUN cargo build --release && strip target/release/mahsa

# ── stage 2: Maisha API + the bundled Mahsa binary ────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Tesseract for the OCR pipeline (expense receipts / vault scans) — degrades if absent, but the
# demo may as well have it.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY api/pyproject.toml ./
COPY api/app ./app
COPY api/alembic.ini ./
COPY api/alembic ./alembic
RUN pip install --upgrade pip && pip install ".[ocr,pg]"

# Mahsa binary from stage 1 — reached at http://127.0.0.1:8088 (start.sh runs it in-process).
COPY --from=mahsa-build /build/target/release/mahsa /usr/local/bin/mahsa

COPY infra/render/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh && mkdir -p /data

EXPOSE 8000
CMD ["/usr/local/bin/start.sh"]
