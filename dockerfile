# ── Stage 1: Python dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS base

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system packages needed by Pillow, SQLite, and general builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libsqlite3-dev \
    libjpeg-dev \
    libpng-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer cache optimisation)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Application ──────────────────────────────────────────────────────
FROM base AS app

WORKDIR /app

# Copy the entire project
COPY . .

# Create directories the app writes to at runtime
RUN mkdir -p uploads instance

# Non-root user for security
RUN addgroup --system freshchef && \
    adduser  --system --ingroup freshchef freshchef && \
    chown -R freshchef:freshchef /app

USER freshchef

# Expose the port Gunicorn will listen on
EXPOSE 5051

# Healthcheck — hits the landing page
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5051/ || exit 1

# 1 worker — SD image generation runs in background threads inside the process.
# Multiple workers each load the full SD model into RAM (4-10 GB each!) and
# still can't run inference in parallel on MPS/CPU, so they just waste memory
# and cause OOM kills (the "SIGKILL perhaps out of memory" you see in logs).
#
# --timeout 0    = never kill a worker for taking too long. SD generation on
#                  MPS/CPU can take several minutes per image — any finite
#                  timeout will kill the worker mid-generation.
# --threads 8    = handle concurrent HTTP requests (image polling, page loads)
#                  while the single worker's background thread generates images.
# --graceful-timeout 300 = give in-flight SD jobs 5 min to finish on shutdown.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5051", \
     "--workers", "1", \
     "--threads", "8", \
     "--timeout", "0", \
     "--graceful-timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "run:app"]