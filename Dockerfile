# syntax=docker/dockerfile:1
FROM python:3.12-slim

# WeasyPrint native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[dev]"

COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
