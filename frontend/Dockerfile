FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY --from=builder /app/dist ./dist

EXPOSE 5173

ENV VITE_API_URL=http://backend:8000

CMD ["npx", "serve", "-s", "dist", "-l", "5173"]