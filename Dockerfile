# ==========================================
# Etapa 1: Builder
# ==========================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install .

# ==========================================
# Etapa 2: Runtime de Producción
# ==========================================
FROM python:3.12-slim AS runtime

LABEL maintainer="public@raupulus.dev"
LABEL org.opencontainers.image.description="Social Stats Read-Only API & WebSockets Server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME="/tmp" \
    XDG_CACHE_HOME="/tmp/.cache" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000"

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /tmp -s /sbin/nologin appuser && \
    mkdir -p /app/config /app/data && \
    chown -R appuser:appgroup /app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup config/profiles.example.json /app/config/profiles.example.json
COPY --chown=appuser:appgroup config/profiles.example.yaml /app/config/profiles.example.yaml

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('APP_PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health')" || exit 1

CMD ["sh", "-c", "exec uvicorn social_stats.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000} --ws-ping-interval 20 --ws-ping-timeout 20"]
