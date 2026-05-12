# Prism Sentinel — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/sentinel)
# so that uv workspace dependencies (prism-schemas, prism-mcp) resolve.
# The sentinel also bundles the MCP ASGI sub-app at /mcp.
# NOTE: sentinel imports trader.config and trader.chain at runtime,
# so the trader package must also be present in the image.

FROM python:3.12-slim
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace root config (defines [tool.uv.workspace] members)
COPY pyproject.toml .
COPY uv.lock .

# Copy shared schemas package (workspace member)
COPY packages/schemas-python/ packages/schemas-python/

# Copy MCP package (workspace member — sentinel depends on prism-mcp)
COPY apps/mcp/pyproject.toml apps/mcp/
COPY apps/mcp/src/ apps/mcp/src/

# Copy trader package (not a declared dep, but sentinel imports trader.config & trader.chain)
COPY apps/trader/pyproject.toml apps/trader/
COPY apps/trader/src/ apps/trader/src/

# Copy sentinel app (workspace member)
COPY apps/sentinel/pyproject.toml apps/sentinel/
COPY apps/sentinel/src/ apps/sentinel/src/

# Install all workspace dependencies via uv sync
RUN uv sync --frozen --no-dev --package prism-sentinel --package prism-trader

EXPOSE 3202
CMD ["uv", "run", "--no-dev", "--package", "prism-sentinel", "uvicorn", "sentinel.main:app", "--host", "0.0.0.0", "--port", "3202"]
