# Prism MCP — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/mcp) so uv workspace
# dependencies (prism-schemas, prism-calibration) resolve consistently.

FROM python:3.12-slim
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root config.
COPY pyproject.toml .
COPY uv.lock .

# Copy workspace packages needed by prism-mcp and the root CLI dependency.
COPY packages/schemas-python/ packages/schemas-python/
COPY packages/calibration-python/ packages/calibration-python/

# Copy MCP app.
COPY apps/mcp/pyproject.toml apps/mcp/
COPY apps/mcp/src/ apps/mcp/src/

RUN uv sync --frozen --no-dev --package prism-mcp

EXPOSE 3204
CMD ["uv", "run", "--no-dev", "--package", "prism-mcp", "python", "-m", "prism_mcp"]
