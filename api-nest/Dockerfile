# Maisha API (NestJS) — multi-stage build. Runtime image carries only prod deps + dist.
FROM node:20-bookworm AS builder
WORKDIR /app
# better-sqlite3 (dev/test dep) compiles a native binding — needs a toolchain in the builder.
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/assets ./assets
COPY --from=builder /app/package.json ./package.json
# Drop root: run as the unprivileged `node` user shipped in the base image.
USER node
EXPOSE 8000
CMD ["node", "dist/main.js"]
