# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (none needed beyond base image today, but leaving the hook here)
# RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user
RUN useradd --create-home --uid 10001 intake
USER intake

COPY --chown=intake:intake gemstone_intake/ ./gemstone_intake/
COPY --chown=intake:intake app/ ./app/

EXPOSE 8080

# Gunicorn: 2 workers is enough for the pipeline's workload (CPU-bound Excel
# parsing). Bump `--workers` if you scale up. 120s timeout for large batches.
# Longer timeout: each row takes ~3s (2s AGL rate limit + Gemini latency).
# 600s accommodates a batch of up to ~200 stones in one request.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app.app:app"]
