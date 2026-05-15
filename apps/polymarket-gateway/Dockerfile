# Prism Polymarket Gateway — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/polymarket-gateway)
# so that pnpm workspace dependencies resolve.
# TypeScript is compiled with tsc and run with node dist/index.js.

FROM node:22-slim AS base
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
# Copy all workspace configuration files
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
# Copy gateway package.json
COPY apps/polymarket-gateway/package.json apps/polymarket-gateway/
COPY packages/builder-codes/package.json packages/builder-codes/
COPY packages/builder-codes/src/ packages/builder-codes/src/
# Install ALL workspace dependencies (including devDeps for tsc)
RUN pnpm install --frozen-lockfile || pnpm install

# --- Build ---
FROM base AS builder
COPY --from=deps /app/ ./
# Copy gateway source and config
COPY apps/polymarket-gateway/src/ apps/polymarket-gateway/src/
COPY apps/polymarket-gateway/tsconfig.json apps/polymarket-gateway/
COPY apps/polymarket-gateway/package.json apps/polymarket-gateway/
# Compile TypeScript to dist/
WORKDIR /app/apps/polymarket-gateway
RUN pnpm run build

# --- Runner ---
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3203

# Copy workspace config + package.jsons for both gateway and builder-codes
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/polymarket-gateway/package.json apps/polymarket-gateway/
COPY packages/builder-codes/package.json packages/builder-codes/
# Copy builder-codes source (needed for workspace install)
COPY --from=builder /app/packages/builder-codes/src/ packages/builder-codes/src/
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate && pnpm install --prod

# Copy compiled output
COPY --from=builder /app/apps/polymarket-gateway/dist/ ./dist/

EXPOSE 3203
CMD ["node", "dist/index.js"]
