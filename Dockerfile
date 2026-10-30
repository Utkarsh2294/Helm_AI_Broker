ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.6
COPY pyproject.toml uv.lock ./
COPY packages/engine ./packages/engine
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv export --frozen --extra agents --extra build --no-emit-package helm-engine --no-dev --format requirements-txt --output-file /tmp/requirements.lock >/dev/null && \
    python -m venv .venv && \
    .venv/bin/python -m pip install --disable-pip-version-check --require-hashes --no-deps --prefer-binary --timeout 300 --retries 5 -r /tmp/requirements.lock && \
    uv sync --frozen --extra agents --extra build --no-dev --offline --no-build-isolation-package helm-engine
COPY services ./services
COPY tools ./tools
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/services/api:/app" CREWAI_TRACING_ENABLED=false CREWAI_DISABLE_TELEMETRY=true OTEL_SDK_DISABLED=false
RUN mkdir -p .runtime
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
