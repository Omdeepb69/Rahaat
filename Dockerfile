# ==============================================================================
# Multi-stage Dockerfile for Raahat 2.0 (Resilient Disaster Intelligence Platform)
# Constraints: Non-root execution, minimal attack surface, volume persistence.
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build virtual environment with compiled dependencies
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml /build/
# src/ must be present before pip install because setuptools resolves packages
# from the directory declared in [tool.setuptools.packages.find] where = ["src"]
COPY src/ /build/src/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# ------------------------------------------------------------------------------
# Stage 2: Production runtime image
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime dependencies for PostGIS C extensions & health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*

# Security: Dedicated non-root system user and group
RUN groupadd -g 10001 raahat && \
    useradd -u 10001 -g raahat -s /bin/bash -m raahat

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app/src:/app"
ENV PYTHONUNBUFFERED=1

# Copy application code and assets
COPY --chown=raahat:raahat alembic.ini pyproject.toml /app/
COPY --chown=raahat:raahat src/ /app/src/
COPY --chown=raahat:raahat field_app/ /app/field_app/
COPY --chown=raahat:raahat operator_console/ /app/operator_console/
COPY --chown=raahat:raahat citizen_portal/ /app/citizen_portal/
COPY --chown=raahat:raahat dashboard/ /app/dashboard/
COPY --chown=raahat:raahat evaluation/ /app/evaluation/
COPY --chown=raahat:raahat deployment/ /app/deployment/

RUN chmod +x /app/deployment/scripts/entrypoint.sh

# Temporary directory permissions for non-root user (heartbeat files)
RUN mkdir -p /tmp && chmod 1777 /tmp

USER raahat

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/app/deployment/scripts/entrypoint.sh"]
CMD ["api"]
