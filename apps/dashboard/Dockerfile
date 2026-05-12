# Prism Dashboard — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/dashboard)
# so that pnpm workspace packages (@prism/schemas, @prism/arc-contracts) resolve.

FROM node:22-slim AS base
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
# Copy workspace config and lockfile from root
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
# Copy workspace packages needed by dashboard
COPY packages/schemas-typescript/package.json packages/schemas-typescript/
COPY packages/schemas-typescript/src/ packages/schemas-typescript/src/
COPY packages/arc-contracts/package.json packages/arc-contracts/
COPY packages/arc-contracts/src/ packages/arc-contracts/src/
# Copy dashboard package files
COPY apps/dashboard/package.json apps/dashboard/
# Install dependencies from root (resolves workspace:*)
# Allow esbuild and sharp build scripts via CLI config
RUN pnpm install --filter=prism-dashboard... --config.onlyBuiltDependencies="esbuild,sharp" --frozen-lockfile || \
    pnpm install --filter=prism-dashboard... --config.onlyBuiltDependencies="esbuild,sharp"

# --- Build ---
FROM base AS builder
COPY --from=deps /app/ ./
# Copy dashboard source
COPY apps/dashboard/ apps/dashboard/
# Build from the dashboard directory (outputFileTracingRoot = monorepo root)
WORKDIR /app/apps/dashboard
RUN pnpm build

# --- Runner ---
FROM node:22-slim AS runner
ENV NODE_ENV=production
ENV PORT=3200
WORKDIR /app

# Copy standalone output — Next.js traces from monorepo root,
# so the structure is apps/dashboard/.next/standalone/{apps/dashboard/server.js, ...}
COPY --from=builder /app/apps/dashboard/.next/standalone ./
COPY --from=builder /app/apps/dashboard/.next/static ./apps/dashboard/.next/static
COPY --from=builder /app/apps/dashboard/public ./apps/dashboard/public

EXPOSE 3200
# server.js is at apps/dashboard/server.js in the standalone output
CMD ["node", "apps/dashboard/server.js"]
