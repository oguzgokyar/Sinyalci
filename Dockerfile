# Stage 1: Build React + Tailwind Web UI
FROM node:22-alpine AS web-builder
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/ ./
RUN npm run build

# Stage 2: Lightweight Python 3.12 VPS Runtime (FastAPI + OpenCV + RapidOCR + Git Updater)
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libglib2.0-0 \
    libgl1 \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
COPY profiles/ ./profiles/
COPY templates/ ./templates/
COPY agent/ ./agent/
COPY --from=web-builder /web/dist ./web/dist

RUN pip install --no-cache-dir -e ".[ocr]"

ENV TRADER_ENV=vps
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
