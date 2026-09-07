FROM node:24-slim AS web-builder

WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/agent \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY agent ./agent
COPY scripts/start_railway_service.py ./scripts/start_railway_service.py
COPY scripts/serve_web_static.py ./scripts/serve_web_static.py
COPY --from=web-builder /web/dist ./web/dist

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

CMD ["python", "scripts/start_railway_service.py"]
