FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host 0.0.0.0 is required so the dev server is reachable through the
# container's published port; vite.config.ts binds 127.0.0.1 for non-Docker
# local dev, so that stays untouched and this overrides it for the container.
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
