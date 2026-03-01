FROM node:20-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json ./package.json
COPY frontend/package-lock.json ./package-lock.json
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build


FROM nginx:latest

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
