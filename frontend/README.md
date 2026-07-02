# Gamma Verification Dashboard

Modern React + Vite + TypeScript dashboard for the gamma 3-way (Python golden ↔
SystemC ↔ RTL) bit-exact scoreboard, served by the FastAPI api-server in
`../api`. The api-server also proxies an RTL-assistant chat through the
**Hermes Gateway** (the OpenAI-compatible agent server, mirroring the sibling
`ai_driven_rtl` project).

## Architecture

```
browser ──/api/*──▶ Vite dev proxy ──▶ FastAPI api-server (:8012)
                                          ├─ GET  /health
                                          ├─ GET  /verification     (live golden-model scoreboard)
                                          ├─ GET  /analyze          (QoR score/grade, verilator+yosys)
                                          ├─ GET  /drc              (coded RTL design-rule report)
                                          ├─ GET  /lint             (verilator lint)
                                          ├─ POST /signoff          (lint→design→synth→3-way regression)
                                          ├─ GET  /telemetry/{kind} (run trends: signoff | verification)
                                          └─ POST /chat ──▶ Hermes Gateway (:8643 /v1/chat/completions)

The QoR/DRC/sign-off/telemetry endpoints are a self-contained port of the
sibling `ai_driven_rtl` project's RTL tooling, calibrated for this design's
portable Verilog-2001 (so `reg`/`wire` and `always @` are not penalized).
```

In production `npm run build` emits `dist/`, which the api-server serves
directly (single container) — the same `/api/*` paths work because the backend
strips the prefix in-process.

## Run

```sh
# 1. Backend (from repo root, venv active):
pip install -r api/requirements.txt
uvicorn api.server:app --host 127.0.0.1 --port 8012

# 2. Frontend dev server (separate terminal):
cd frontend && npm install && npm run dev      # http://127.0.0.1:5173

# or production: build then let the backend serve it
cd frontend && npm run build                   # then open http://127.0.0.1:8012/
```

## Connecting the Hermes Gateway (live chat)

`/api/chat` returns **503** until the gateway key is configured. The gateway
itself runs separately (e.g. `rtlgateway gateway run`, default `:8643`).

Set the key in `../.env` (gitignored):

```
HERMES_GATEWAY_BASE_URL=http://127.0.0.1:8643/v1
HERMES_GATEWAY_API_KEY=<the gateway's API_SERVER_KEY>
```

`/api/health` reports `has_key` and the resolved `gateway_base_url`; the UI
shows a `hermes: connected / no key` pill accordingly.

## Offline fallback

If the backend is unreachable, the dashboard falls back to the bundled
`public/results.json` snapshot (regenerate with
`PYTHONPATH=tb:golden python scripts/gen_dashboard_data.py`).
