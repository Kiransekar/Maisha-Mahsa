# PaddleOCR sidecar. Heavy (paddle + models ~1GB) — built only under the `ocr` compose profile.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir \
    paddlepaddle paddleocr fastapi "uvicorn[standard]" pillow python-multipart numpy
COPY app.py .
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
