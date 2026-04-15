# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim
WORKDIR /app

# Runtime libs: libpq5 (postgres), fonts for PDF generation (replaces Windows fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project source (kiddora_root contents → /app)
COPY . .

# Startup script
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# Azure App Service uses $PORT; fallback to 8000
EXPOSE 8000

# Non-root user
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /startup.sh

USER appuser
CMD ["/startup.sh"]