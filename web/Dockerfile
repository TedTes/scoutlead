FROM node:24-slim AS builder

WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
ARG VITE_API_BASE_URL
ARG VITE_CLERK_PUBLISHABLE_KEY
RUN : "${VITE_API_BASE_URL:?Set VITE_API_BASE_URL on the web service}" \
    && : "${VITE_CLERK_PUBLISHABLE_KEY:?Set VITE_CLERK_PUBLISHABLE_KEY on the web service}" \
    && npm run build


FROM node:24-slim

ENV NODE_ENV=production

WORKDIR /web

COPY server.mjs ./server.mjs
COPY --from=builder /web/dist ./dist

CMD ["node", "server.mjs"]
