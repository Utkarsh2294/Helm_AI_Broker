FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra agents --no-dev
COPY services ./services
COPY tools ./tools
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/services/api:/app" CREWAI_TRACING_ENABLED=false OTEL_SDK_DISABLED=true
RUN mkdir -p .runtime
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
