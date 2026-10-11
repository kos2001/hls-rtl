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

## Workspace interface

The dashboard opens with the reference model, test-set metrics, an interactive
RGB LUT chart, and the evidence available for Python, SystemC, and RTL. The
sidebar groups design inspection, verification, and assistant tools. Detailed
EDA views retain the design navigator, selection inspector, and resizable
transcript as optional docks.

- `⌘K` / `Ctrl+K`: search pages, patterns, and actions with keyboard navigation.
- Views use URL hashes such as `#scoreboard`, supporting bookmarks and browser history.
- Theme and language preferences persist locally; the interface supports English and Korean.
- Pattern search and status filters work in the scoreboard. Selecting a pattern opens its inspector.
- Results export as JSON. Transcript export includes the full session, including hidden or filtered messages.
- Small screens use a navigation drawer. The main content scrolls independently of the shell.

`/verification` currently calculates **expected reference outputs**, rather
than reading measured simulator output. Its `evidence_kind: "reference"`
metadata is preserved in exports. Reference data and older untagged snapshots
never show a measured PASS; the UI hides their mirrored RTL hashes and displays
“Not measured”. Run **Sign-off** for a measured stage report. Skipped stages
remain missing evidence. The chart visualizes the golden LUT equation rather
than captured waveform samples, and honors the `GAMMA` environment override.

## Frontend structure

`App.tsx` composes the workspace. `hooks/useWorkbench.ts` owns data fetching
and serializes refresh/sign-off requests. `navigation.ts` defines the typed
view registry; `hooks/useView.ts` handles URL navigation. `views/` contains the
extracted scoreboard, quality, sign-off, flows, and assistant components.
Heavy tools load on demand. `components/` contains shared icons, the search
dialog, and the view error boundary. `styles/workspace.css` owns the product
tokens and responsive shell; `index.css` contains the detailed EDA viewer styles.

## UI checks

```sh
npm run build
WORKBENCH_URL=http://127.0.0.1:5173/ npm run check:workspace
WORKBENCH_URL=http://127.0.0.1:5173/ npm run check:responsive
```

The browser checks use an existing Playwright installation. Set
`PLAYWRIGHT_PATH` to its package path if it is outside the project, and
`PLAYWRIGHT_EXECUTABLE_PATH` when using a separately installed Chromium.
`SCREENSHOT_DIR` optionally saves dark desktop, Korean light desktop, and
mobile captures during the workspace check.

`check:workspace` isolates the API with fixtures and checks provenance,
interactive LUT endpoints, search, filters, exports, sign-off request/failure
states, offline recovery, localization, theme persistence, and mobile history.
It never starts a real simulator or calls the agent gateway.
`check:responsive` visits all 11 views at 10 viewport sizes, including mobile,
tablet, and 400% zoom equivalents, and fails on overflow or collapsed content.
