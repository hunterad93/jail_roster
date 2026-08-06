FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PORT=8080
CMD ["uv", "run", "uvicorn", "jail_roster.web:app", "--host", "0.0.0.0", "--port", "8080"]
