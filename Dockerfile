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

# IMPORTANT: ONE worker + many threads. Background jobs live in this process's
# memory (JOBS dict), so every poll to /jobs/<id> must hit the same process.
# Threads handle concurrent requests; the pipeline is I/O-bound (AGL + Gemini).
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--threads", "8", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app.app:app"]
