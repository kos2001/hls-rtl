# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A bit-exact verification skeleton for a **gamma-correction pixel core**, kept in
lockstep across three independent models. A small FastAPI **api-server** and a
React **dashboard** sit on top to surface results and RTL quality.

Two layers, do not confuse them:
- **Verification core** (`golden/`, `systemc/`, `rtl/`, `tb/`, `tests/`, `scripts/`) — the actual hardware + its 3-way scoreboard.
- **Web layer** (`api/`, `frontend/`) — serves verification results and proxies an RTL-assistant chat through the Hermes Gateway. Ported/adapted from the sibling `../ai_driven_rtl` project.

## The bit-exact contract (most important thing to know)

Three models must produce **identical** output for the same stimulus + LUTs:
1. `golden/gamma_golden.py` — numpy reference, the **single source of truth**.
2. `systemc/gamma_sc.{h,cpp}` — cycle-accurate SystemC mirror.
3. `rtl/gamma.v` — Verilog DUT (1 pixel/cycle, ready/valid, per-channel LUT).

Equality is verified per pattern via SHA-256 frame hashes. The DUT contract:
a parameterizable elastic **FIFO** (`FIFO_DEPTH`, default 8) with
`in_ready = (count != FIFO_DEPTH)` — registered occupancy only, no
combinational out_ready→in_ready path — **1-cycle latency** from accepted
input to valid output (the FIFO only fills during a downstream stall), async
active-low reset clearing pointers/occupancy. The RTL is
intentionally **portable Verilog-2001** (`reg`/`wire`, `always @`) — do not
"modernize" it to SystemVerilog without reason; the cocotb flow runs under
`TOPLEVEL_LANG=verilog`.

**When changing precision/depth (the Δ-propagation drill):** bump `LUT_SIZE`/
`PIXEL_W`/`LUT_DEPTH` together in `gamma_golden.py`, `gamma.v`, AND `gamma_sc.h`
— the three must stay aligned or the scoreboard breaks. `gamma.v` also asserts
`LUT_DEPTH == 2**PIXEL_W` at elaboration.

The canonical test set lives in `tb/test_set.py` (patterns + per-channel LUTs).
**Pattern order is an append-only contract** — `build/sc_out.txt` is consumed
sequentially, so only append new patterns. Per-channel gammas are deliberately
distinct (R=2.2, G=1.8, B=2.8) so a swapped/crossed channel cannot alias to a
bit-exact pass.

## Commands

```sh
# Setup (cocotb needs an activated venv)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # numpy, cocotb<2.0, pytest
pip install -r api/requirements.txt       # fastapi, uvicorn, httpx, pydantic, python-dotenv

# Full regression (unit tests -> SystemC inputs -> SystemC sim -> cocotb 3-way)
./scripts/run_3way.sh

# Layers individually
python -m pytest tests/ -q                # L0: unit tests, no simulator
cd tb && make                             # L1+L2: directed + 3-way RTL tests (verilator)

# One cocotb test (TESTCASE = function name in tb/test_gamma.py)
cd tb && make TESTCASE=test_single_pixel_latency
cd tb && make WAVES=1                      # add VCD dump (~30% slower)

# Build the optional standalone SystemC sim (enables the SC compare)
g++ -std=c++17 -I$SYSTEMC_HOME/include -L$SYSTEMC_HOME/lib \
    systemc/sim_main.cpp systemc/gamma_sc.cpp -lsystemc -o build/gamma_sc_sim

# Web layer
uvicorn api.server:app --host 127.0.0.1 --port 8012     # api-server (serves frontend/dist if built)
cd frontend && npm install && npm run dev               # dashboard dev server (proxies /api -> :8012)
cd frontend && npm run build                            # production build (tsc -b && vite build)
```

### Testbench knobs (env vars for `make` / cocotb)
- `GAMMA=<float>` — override all three channels with one gamma (legacy single-gamma flow).
- `BP_PROFILE` — `split` (default: data coverage then protocol coverage), `full` (every pattern × every backpressure profile, nightly), `single` (one env-defined profile).
- `BP_SEED`, `BP_IN_STALL`, `BP_OUT_STALL`, `BP_IN_BURST`, `BP_OUT_BURST` — control the backpressure profile (only with `BP_PROFILE=single`). Backpressure changes ordering, not values; bit-exactness must still hold.

If `build/sc_out.txt` is absent the SystemC compare is **skipped** (not failed) —
the RTL-vs-golden comparison still gates. See `TESTPLAN.md` for the L0/L1/L2
layer rationale and known gaps.

## Web layer architecture

`api/server.py` (FastAPI) serves the SPA and exposes, under `/api/*` (the prefix
is stripped in-process so the same client works behind the dev proxy and the
built container):
- `GET /verification` — live scoreboard, computed from the golden model via `scripts/gen_dashboard_data.py::build_results()`; SHA hashes match the cocotb run.
- `GET /analyze`, `/drc`, `/lint` — RTL QoR (verilator lint + yosys synth + structural checks → 0-100 score), design-rule report. Implemented in `api/rtl_qor.py`, **calibrated for Verilog-2001** (does not penalize `reg`/`wire` or `always @`).
- `POST /signoff` — lint → design → synthesize → **the real 3-way cocotb regression** (`make -C tb`) → consolidated verdict (`api/signoff.py`).
- `GET /telemetry/{kind}` — run trends archived to `runs/` (`api/telemetry.py`).
- `GET /skills` — which agent skills the gateway's **serving profile** actually has, vs. what this project wants (`api/skills.py`). The gateway serves one profile; naming a skill it lacks is a silent no-op, so the directive is built from live discovery, never a hard-coded list. Source of truth is `skills/`; install with `scripts/sync_hermes_skills.py`.
- `GET /waveform`, `GET /waveform/status`, `POST /waveform/run` — VCD extraction for the waveform viewer (`api/waveform.py`). `tb/dump.vcd` comes from the traced regression (`make -C tb WAVES=1`, ~30% slower); elaboration parameters are listed separately rather than plotted.
- `GET /schematic` — layered RTL netlist graph from `yosys proc + opt_clean` (`api/schematic.py`). No graphviz dependency: the browser draws it. Cells carry their source line for schematic→RTL cross-probing.
- `GET /kb/stats`, `/kb/search?q=`, `/kb/context?q=` — the retrieval knowledge base (`api/knowledge.py`) that grounds `/chat` and `/plan`. Chunks are semantic units (an always-block, a function, a doc section) over `rtl/ golden/ systemc/ tb/` plus the markdown docs and the live results; retrieval is **BM25 lexical, deliberately not embeddings** — the queries are identifiers (`in_ready`, `FIFO_DEPTH`) that vector similarity blurs. Korean queries are bridged by a domain glossary (`KO_TERMS`). Pinned chunks (module contract, port list, live pass/fail) are always injected; the rest is retrieved per question. The index rebuilds on source mtime change.
- `POST /chat` — RTL-assistant routed through the **Hermes Gateway** (`api/hermes_engine.py`, an OpenAI-compatible `/v1/chat/completions` agent server). Returns **503** until `HERMES_GATEWAY_API_KEY` is set in `.env`; the gateway runs separately (default `:8643`, the `rtlgateway` profile, which sets `model_name: hermes-agent`). Config in `api/config.py`. The response carries the `citations` that grounded it.

`frontend/` is React 19 + Vite 7 + TypeScript; data adapter in `src/api.ts`
falls back to bundled `public/results.json` when the backend is unreachable.
Regenerate that snapshot with
`PYTHONPATH=tb:golden python scripts/gen_dashboard_data.py`.

The UI is laid out like a commercial EDA tool (Cadence/Synopsys): menu bar, run
toolbar, **design navigator** (left), tabbed work area, **properties inspector**
(right), **tool transcript** (bottom), status bar. Two themes via `data-theme`.
Panes are fluid (`clamp()` defaults in CSS custom properties) and draggable
(`src/Splitter.tsx`, persisted); View ▸ Reset layout clears a stored size.
Verify layout changes with `npm run check:responsive` (8 viewport sizes x 6
views; needs a playwright install — see the script header). **Test zoom by
resizing the viewport, not with the CSS `zoom` property** — `zoom` scales boxes
without moving the media queries, so it reports failures real zoom never hits.
Every flow routes through `src/log.ts::traced()`, so the transcript is a complete
severity-tagged record of the session — the format is specified by the
`eda-transcript-conventions` skill, which means agent output and tool output read
alike. Views: Scoreboard, Waveform (`src/Waveform.tsx`, canvas), Schematic
(`src/Schematic.tsx`, SVG), Quality, Sign-off, Flows, Knowledge (`src/Knowledge.tsx`
— the same retrieval the agent gets, with scores, so a bad answer can be traced to
retrieval vs. the model), Assistant.

## Conventions

- The web layer is **self-contained** — it does not import from `../ai_driven_rtl`; relevant logic was ported in. Keep it that way.
- Python imports across the verification core rely on `sys.path` injection of `golden/` and `tb/` (see top of `tb/test_gamma.py` and `scripts/gen_dashboard_data.py`). Run scripts with `PYTHONPATH=tb:golden` or from the locations that set this up.
- `scripts/jira_*.py` are project-management glue, unrelated to the DUT.
