FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/agent \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY agent ./agent
COPY scripts/start_railway_service.py ./scripts/start_railway_service.py

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

CMD ["python", "scripts/start_railway_service.py"]
