# syntax=docker/dockerfile:1

# PDF Tools — production image with LibreOffice, Tesseract, Ghostscript
# Hardening notes: non-root user, no baked-in secrets, gunicorn timeout for
# long jobs. Compose adds cap_drop / no-new-privileges / resource limits.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PDF_TOOLS_HOST=0.0.0.0 \
    PDF_TOOLS_PORT=5000 \
    PDF_TOOLS_DEBUG=0 \
    PDF_TOOLS_CONFIG=production \
    PUBLIC_DEPLOY=false

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
RUN mkdir -p instance/uploads instance/outputs /tmp/pdf-tools \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /tmp/pdf-tools

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3)"

# SECRET_KEY must be provided at runtime (compose / -e). Weak defaults refuse to start.
# Longer timeout for OCR / LibreOffice jobs
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--timeout", "300", "--graceful-timeout", "30", "run:app"]
