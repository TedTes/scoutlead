FROM node:24-slim AS builder

WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
RUN npm run build


FROM node:24-slim

ENV NODE_ENV=production

WORKDIR /web

COPY server.mjs ./server.mjs
COPY --from=builder /web/dist ./dist

CMD ["node", "server.mjs"]
