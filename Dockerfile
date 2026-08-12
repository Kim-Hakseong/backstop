FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backstop/ ./backstop/
COPY subject_agent/ ./subject_agent/
COPY api/ ./api/

ENV PYTHONPATH=/app
ENV PORT=8080

CMD exec uv run --no-dev uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
