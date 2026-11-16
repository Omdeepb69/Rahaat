# RAAHAT backend image: API and worker share it. Frontend is deployed separately.
FROM python:3.11-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
# Install exactly the locked dependency versions, then the package itself.
RUN pip install uv==0.10.8 \
 && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
 && pip install -r requirements.txt
COPY src ./src
RUN pip install --no-deps .

FROM python:3.11-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 raahat && useradd -u 10001 -g raahat -m -s /usr/sbin/nologin raahat \
 && mkdir -p /data/audio && chown raahat:raahat /data/audio
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=raahat:raahat alembic.ini ./
COPY --chown=raahat:raahat src ./src
COPY --chown=raahat:raahat --chmod=0755 scripts/container-entrypoint.sh /usr/local/bin/raahat-entrypoint
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    AUDIO_STORAGE_DIR=/data/audio HOST=0.0.0.0 PORT=8000
USER raahat
EXPOSE 8000
ENTRYPOINT ["raahat-entrypoint"]
CMD ["api"]
