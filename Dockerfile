# syntax=docker/dockerfile:1
#
# Single-container image: build the React dashboard, then serve it + the API
# from one uvicorn process. EDA tools are installed so /analyze, /drc, /synth,
# and /signoff work inside the container. The Hermes Gateway runs separately;
# point HERMES_GATEWAY_BASE_URL at it (host.docker.internal by default).

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HERMES_GATEWAY_BASE_URL=http://host.docker.internal:8643/v1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl g++ make verilator yosys \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY api/requirements.txt ./api/requirements.txt
RUN pip install -r requirements.txt && pip install -r api/requirements.txt

COPY rtl ./rtl
COPY golden ./golden
COPY systemc ./systemc
COPY tb ./tb
COPY scripts ./scripts
COPY api ./api
COPY README.md ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8012

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8012/api/health || exit 1

CMD ["python", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8012"]
