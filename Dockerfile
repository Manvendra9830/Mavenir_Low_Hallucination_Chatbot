# ── Stage 1: Frontend Build ──
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Backend ──
FROM python:3.12-slim AS production
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# Frontend static files (served by FastAPI or reverse proxy)
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create storage directories
RUN mkdir -p storage/vector storage/bm25 storage/metadata data/3gpp

# Environment
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
