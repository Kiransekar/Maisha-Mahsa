# Maisha API (FastAPI + HTMX).
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Tesseract system binary for the OCR pipeline (expense receipts / vault scans).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
# alembic.ini + alembic/ must ship in the image: the compose `migrate` service runs
# `alembic upgrade head` in this image (it previously failed — the files were never copied).
COPY alembic.ini ./
COPY alembic ./alembic
# [pg] = psycopg2 so MAISHA_DATABASE_URL can point at Postgres/Supabase (launch path).
RUN pip install --upgrade pip && pip install ".[ocr,pg]"

RUN useradd -r -u 10002 maisha && mkdir -p /data && chown maisha /data
USER maisha

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
