FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Small, self-contained runtime (not tied to the uv workspace/lock).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir httpx==0.28.1

COPY deployments/entity-linkage/entity_linkage.py /app/entity_linkage.py

# Defaults (override via compose/env)
ENV API_URL="http://api:8000" \
    ENTITY_LINKAGE_MODE="oneshot" \
    ENTITY_LINKAGE_SLEEP_SECONDS="10" \
    ENTITY_LINKAGE_TIMEOUT_SECONDS="10" \
    ENTITY_LINKAGE_MAX_RETRIES="60" \
    ENTITY_LINKAGE_RETRY_BACKOFF_SECONDS="1" \
    ENTITY_LINKAGE_LOG_LEVEL="INFO"

CMD ["python", "/app/entity_linkage.py"]
