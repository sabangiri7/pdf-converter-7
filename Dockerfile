# syntax=docker/dockerfile:1

# PDF Tools — production image with LibreOffice, Tesseract, Ghostscript
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PDF_TOOLS_HOST=0.0.0.0 \
    PDF_TOOLS_PORT=5000 \
    PDF_TOOLS_DEBUG=0 \
    PDF_TOOLS_CONFIG=default \
    PDF_TOOLS_SECRET_KEY=change-me-in-production

WORKDIR /app

# System deps for Office → PDF and OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        tesseract-ocr \
        tesseract-ocr-eng \
        ghostscript \
        fonts-liberation \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt gunicorn==23.0.0

COPY . .

# Runtime upload/output dirs (also mounted via compose if desired)
RUN mkdir -p instance/uploads instance/outputs \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3)"

# Longer timeout for OCR / LibreOffice jobs
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--timeout", "300", "--graceful-timeout", "30", "run:app"]
