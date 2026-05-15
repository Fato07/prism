# Prism Dashboard — Dockerfile for Railway deployment
# Build context MUST be the monorepo root (not apps/dashboard)
# so that pnpm workspace packages (@prism/schemas, @prism/arc-contracts) resolve.

FROM node:22-slim AS base
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
# Copy all workspace configuration files
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
# Copy workspace packages needed by dashboard
COPY packages/schemas-typescript/package.json packages/schemas-typescript/
COPY packages/schemas-typescript/src/ packages/schemas-typescript/src/
COPY packages/arc-contracts/package.json packages/arc-contracts/
COPY packages/arc-contracts/src/ packages/arc-contracts/src/
COPY packages/builder-codes/package.json packages/builder-codes/
COPY packages/builder-codes/src/ packages/builder-codes/src/
# Copy dashboard package files (includes pnpm.onlyBuiltDependencies)
COPY apps/dashboard/package.json apps/dashboard/
# Install ALL workspace dependencies (not filtered, to ensure root config is applied)
# The root package.json has pnpm.onlyBuiltDependencies for esbuild and sharp
RUN pnpm install --frozen-lockfile || pnpm install

# --- Build ---
FROM base AS builder
COPY --from=deps /app/ ./
# Copy dashboard source only (other apps not needed)
COPY apps/dashboard/ apps/dashboard/
# Ensure public directory exists (Next.js expects it even if empty)
RUN mkdir -p /app/apps/dashboard/public
# Build from the dashboard directory (outputFileTracingRoot = monorepo root)
WORKDIR /app/apps/dashboard
# NEXT_PUBLIC_* vars are client-side and must be baked into the client JS at
# build time. Turbopack does not inline Docker ENV into the client bundle, so
# we materialise .env.local from build args. Railway sets these via
# `railway variables --build-arg` (or its equivalent build-time vars).
#
# IMPORTANT: ARC_RPC_URL embeds an Arc-canteen-issued bearer token in the URL
# path. Never hard-code it in this Dockerfile or anywhere else in version
# control — if you accidentally commit a real key, rotate it immediately with
# `arc-canteen rotate-rpc-key` and update Railway env vars.
ARG NEXT_PUBLIC_REOWN_PROJECT_ID
ARG ARC_RPC_URL
ARG NEXT_PUBLIC_ARC_RPC_URL
ARG NEXT_PUBLIC_IPFS_GATEWAY="https://gateway.pinata.cloud/ipfs"
ARG NEXT_PUBLIC_SITE_URL="https://prism-dashboard-production-e6e3.up.railway.app"
RUN printf '%s\n%s\n%s\n%s\n%s\n' \
      "NEXT_PUBLIC_REOWN_PROJECT_ID=${NEXT_PUBLIC_REOWN_PROJECT_ID}" \
      "ARC_RPC_URL=${ARC_RPC_URL}" \
      "NEXT_PUBLIC_ARC_RPC_URL=${NEXT_PUBLIC_ARC_RPC_URL}" \
      "NEXT_PUBLIC_IPFS_GATEWAY=${NEXT_PUBLIC_IPFS_GATEWAY}" \
      "NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}" \
      > .env.local
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
# Server-side ARC_RPC_URL is provided by Railway env at runtime for the
# /api/rpc/arc proxy route. It is also already inlined into the client bundle
# via NEXT_PUBLIC_ARC_RPC_URL above. Do not hard-code it here.
# server.js is at apps/dashboard/server.js in the standalone output.
CMD ["node", "apps/dashboard/server.js"]
