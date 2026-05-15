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
# NEXT_PUBLIC_* vars are client-side (non-secret) and must be baked into the client JS at build time.
# These are inlined by Next.js during next build and cannot be overridden at runtime.
ENV NEXT_PUBLIC_REOWN_PROJECT_ID=0169b238a503068cc520097200b51458
ENV NEXT_PUBLIC_ARC_RPC_URL=https://rpc.testnet.arc-node.thecanteenapp.com/v1/ARC_RPC_TOKEN_REDACTED
ENV NEXT_PUBLIC_IPFS_GATEWAY=https://gateway.pinata.cloud/ipfs
ENV NEXT_PUBLIC_SITE_URL=https://prism-dashboard-production-e6e3.up.railway.app
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
