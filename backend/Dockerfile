# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY src/herbaguard/__init__.py src/herbaguard/__init__.py
RUN pip install .

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-deps .

RUN useradd --create-home --uid 10001 herbaguard && mkdir -p /data/raw && chown herbaguard /data/raw
USER herbaguard

EXPOSE 8000
# Apply migrations, then serve. Migrations are idempotent.
CMD ["sh", "-c", "alembic upgrade head && uvicorn herbaguard.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]
