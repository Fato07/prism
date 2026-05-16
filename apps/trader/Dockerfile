# Prism Trader — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/trader)
# so that uv workspace dependencies (prism-schemas) resolve.

FROM python:3.12-slim
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root config (defines [tool.uv.workspace] members)
COPY pyproject.toml .
COPY uv.lock .

# Copy shared schemas package (workspace member)
COPY packages/schemas-python/ packages/schemas-python/

# Copy calibration package because the root workspace project exposes it for
# local CLI usage; uv must see the workspace member even though trader does
# not import it at runtime.
COPY packages/calibration-python/ packages/calibration-python/

# Copy trader app (workspace member)
COPY apps/trader/pyproject.toml apps/trader/
COPY apps/trader/src/ apps/trader/src/

# Install all workspace dependencies via uv sync
RUN uv sync --frozen --no-dev --package prism-trader

EXPOSE 3201
CMD ["uv", "run", "--no-dev", "--package", "prism-trader", "uvicorn", "trader.main:app", "--host", "0.0.0.0", "--port", "3201"]
