# Single-service Dockerfile — builds Next.js + runs both backend & frontend
# Railway reads this from the repo root

# ── Stage 1: Build Next.js frontend ──────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 2: Runtime container ───────────────────
FROM python:3.12-slim

# Install system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libraw-dev \
      nodejs \
      npm \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Backend ──────────────────────────────────────
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/main.py ./backend/

# ── Frontend (standalone build) ──────────────────
COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend/public

# ── Start script ─────────────────────────────────
RUN echo '#!/bin/bash\n\
cd /app/backend && uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
cd /app/frontend && PORT=3000 HOSTNAME=0.0.0.0 node server.js\n\
wait' > /app/start.sh && chmod +x /app/start.sh

ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV PORT=3000

CMD ["/app/start.sh"]
