# ── Stage 1: Build frontend ──────────────────────────────
FROM node:22-slim AS frontend-build
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ── Stage 2: Install Python dependencies ─────────────────
FROM python:3.13-slim-bookworm AS python-deps
RUN pip install uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# ── Stage 3: Runtime ─────────────────────────────────────
FROM python:3.13-slim-bookworm

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

# Copy Python virtual environment from stage 2
COPY --from=python-deps /app/backend/.venv /app/backend/.venv

# Copy backend source
COPY backend/ /app/backend/

# Copy built frontend into /app/static (served by FastAPI)
COPY --from=frontend-build /app/frontend/dist /app/static

# Copy seed data
COPY web_app_seed/veeville-templates.json /app/web_app_seed/veeville-templates.json
COPY web_app_seed/veeville-rates.json /app/web_app_seed/veeville-rates.json

# Create outputs directory
RUN mkdir -p /data/outputs

WORKDIR /app/backend

ENV PATH="/app/backend/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
