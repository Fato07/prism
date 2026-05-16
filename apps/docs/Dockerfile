# Prism Docs — Dockerfile for Railway deployment
# Build context MUST be the monorepo root so pnpm workspace resolution works.

FROM node:22-slim AS base
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/docs/package.json apps/docs/
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=deps /app/ ./
COPY apps/docs/ apps/docs/
RUN mkdir -p /app/apps/docs/public
WORKDIR /app/apps/docs
RUN pnpm build

FROM node:22-slim AS runner
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3300
WORKDIR /app

COPY --from=builder /app/apps/docs/.next/standalone ./
COPY --from=builder /app/apps/docs/.next/static ./apps/docs/.next/static
COPY --from=builder /app/apps/docs/public ./apps/docs/public

EXPOSE 3300
CMD ["node", "apps/docs/server.js"]
