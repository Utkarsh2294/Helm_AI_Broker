ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --extra agents --no-dev
COPY services ./services
COPY tools ./tools
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/services/api:/app" CREWAI_TRACING_ENABLED=false CREWAI_DISABLE_TELEMETRY=true OTEL_SDK_DISABLED=false
RUN mkdir -p .runtime
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
