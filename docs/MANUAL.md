# User Manual — Gamma Verification Workbench

## What you are looking at

The workbench exists to answer one question: **is this RTL actually right?**

An agent can write plausible Verilog; it cannot check it. So this project keeps
an independent, executable reference — the Python golden model — and proves each
representation against it, pattern by pattern, with SHA-256 frame hashes.

Everything in the UI is either **evidence** for that claim or a **tool for
producing more of it**. Read it in that spirit: a green number is not the point,
the hash behind it is.

### The one rule

> **A skipped stage is missing evidence, not a pass.**

The workbench applies this everywhere — in sign-off verdicts, in the SystemC
column, in agent answers. When you see `skip`, something did not run; find out
what and decide whether you care.

---

## Start it

```sh
# once
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt api/requirements.txt

# the server (serves the built UI too)
uvicorn api.server:app --host 127.0.0.1 --port 8012
```

Open <http://127.0.0.1:8012>.

For UI development, run the Vite dev server alongside it — it proxies `/api` to
port 8012:

```sh
cd frontend && npm install && npm run dev
```

### What you need installed

| Tool | Needed for | Without it |
|---|---|---|
| **SymbiYosys** (`sby`) + a solver | formal stage of the gate | that stage reports **skip** — missing evidence, not a pass |
| **SystemC** (`brew install systemc`) | the third model in the 3-way scoreboard | that comparison is **skipped** and the scoreboard silently becomes 2-way — build with `scripts/build_systemc.sh` |
| Python 3.10+, `cocotb<2.0` | the regression | nothing works |
| **Verilator ≥ 5.0** | simulation, lint | Scoreboard falls back to the bundled snapshot |
| **yosys** | QoR, schematic, LEC | those views report *unavailable*, not a failure |
| **Icarus Verilog** | 4-state stage of the gate | that stage reports **skip** — X and reset-init bugs become undetectable |
| SystemC 2.3.x | the SystemC rung | that column shows **skipped** |
| Hermes Gateway | Assistant, Planner | those return 503; everything else works |

Nothing here is a hard dependency of the rest. A missing tool degrades one view
and says so.

---

## The window

```
┌──────────────────────────────────────────────────────────────┐
│ menu bar            File · View · Run · Help                 │
├──────────────────────────────────────────────────────────────┤
│ toolbar             Reload · Waveform · Schematic · Sign-off │
├───────────┬──────────────────────────────────┬───────────────┤
│ Design    │  view tabs                       │ Properties    │
│ Navigator │  ────────────────────────────    │ (inspector)   │
│           │  the work area                   │               │
├───────────┴──────────────────────────────────┴───────────────┤
│ Transcript — every action, severity-tagged                   │
├──────────────────────────────────────────────────────────────┤
│ status bar   design · scoreboard · QoR · profile · kb        │
└──────────────────────────────────────────────────────────────┘
```

**Design Navigator (left)** browses the design: the module and its ports, the
three model representations, the 13 test patterns, and the agent skills.
Selecting something describes it on the right — it does *not* change the view.

**Properties (right)** is the inspector for whatever is selected, in the
navigator or by clicking a cell in the schematic.

**Transcript (bottom)** is the tool log. Every action writes a banner, its
findings and a verdict, in the message format commercial tools use:

```
ERROR-[LATCH] gamma.lut_rd: inferred latch — incomplete branch
    rtl/gamma.v:118
```

Filter by **threshold**: clicking `W` shows warnings *and worse*. The text box
filters by tag or content. **Copy** puts the filtered view on the clipboard —
that is the fastest way to hand someone a failure.

### Resizing

Panes are fluid and the dividers are draggable. **Double-click a divider** (or
press Enter on it) to return it to the automatic size. If the layout ever looks
wrong, **View ▸ Reset layout** clears every stored size.

View ▸ also toggles each dock and switches between the dark and light themes.

---

## The views

### Overview
The claim, the proof chain with its live state, what the evidence does *not*
cover, and the design's key facts. Start here.

### Scoreboard
The core evidence: per pattern, the golden / RTL / SystemC frame hashes and
whether they agree. Click a row to inspect it on the right.

Read the caveat at the bottom. The regression runs under **Verilator, which is
2-state** — these hashes prove value equality on these patterns, and say nothing
about X-propagation or reset initialization.

A `— skipped` SystemC hash means `build/sc_out.txt` was absent. That is missing
evidence; the RTL-vs-golden comparison still gated.

### Waveform
A Verdi/SimVision-style viewer over `tb/dump.vcd`.

- **Click** the canvas to place the cursor; the right column shows every
  signal's value at that time.
- **⌘/Ctrl + wheel** zooms around the pointer. **Fit** returns to the full window.
- **Re-simulate** runs the traced regression (`make -C tb WAVES=1`, ~30% slower
  than an untraced run).
- Elaboration parameters (`LUT_DEPTH`, `CH_R`, …) are listed at the bottom
  rather than drawn — they are constants, not waveform traffic.

Internal FIFO state (`count`, `rd_ptr`, `wr_ptr`, `push`, `pop`) is traced, which
is what makes a handshake question answerable here rather than by reasoning.

### Schematic
The RTL netlist from `yosys proc + opt_clean` — RTL-level cells (`MUX`, `DFF`,
`MEM rd`), not gates, because a gate netlist of this design is thousands of
unreadable nodes.

Cells are laid out left-to-right by level; sequential cells cut the feedback
loops, which is why a design with a circular FIFO reads as a straight line.
**Click a cell** to cross-probe: Properties shows its type, width and source
line, and its nets highlight.

### Quality
The deterministic QoR score (0-100) and the design-rule table. Calibrated for
**Verilog-2001** — it does not penalize `reg`/`wire`/`always @`, because that
dialect is a deliberate choice here, not an oversight.

### Sign-off
The ladder: **lint → design → synthesize → simulate**, where `simulate` is the
real cocotb 3-way regression, not a mock. Takes a few seconds.

| Verdict | Meaning |
|---|---|
| `SIGNED_OFF` | every gating stage passed |
| `CONDITIONAL` | non-gating issues remain |
| `REJECTED` | a gating stage failed |

Runs archive to `runs/`, and the sparkline shows the score trend.

### Flows
The four analyses that are not part of the ladder:

- **Progressive-coding oracle** — the representation × pattern equivalence
  matrix, run for real.
- **Adaptive reflection** — given a failure, which pipeline stage is the root
  cause (deterministic; no LLM).
- **Equivalence (LEC)** — yosys sequential equivalence. Paste candidate RTL to
  prove it equals the project RTL; leave it blank for a self-equivalence sanity
  check.
- **Graph RAG** — knowledge-graph neighbourhood of a symbol.

### Improve
The self-improvement loop: **propose → prove → reflect → retry**, bounded.

It leads with what a `PROVEN` verdict does and does not mean, because that is the
only thing keeping the loop honest — an agent that edits RTL and grades itself
converges on plausibility, so here the **oracle decides, not the model**.

- **Evidence gaps** — ranked, deterministic, no gateway needed. This is the
  honest answer to "what should improve next" when everything already passes:
  the next step is rarely more RTL, it is closing a gap in evidence.
- **Prove committed RTL** — runs the gate against `rtl/gamma.v`: lint → design →
  synthesize → **SystemC** → the real cocotb regression → **configs** →
  **4-state** → **formal**. The SystemC stage rebuilds and reruns the third
  model so the scoreboard that follows really is 3-way rather than skipping a
  rung and keeping its name. No LLM anywhere in it. The `configs` stage re-runs the bit-exact
  comparison with `LUT_SYNC_READ=1`: that `generate` branch is not elaborated by
  default, so without it the whole registered-LUT-read path has no coverage —
  which is how mutation testing found it. The 4-state stage re-runs the same tests under Icarus, which
  can represent X: deleting `count <= 0` from the reset branch passes 5/5 under
  Verilator and fails 0/5 under Icarus.
  The formal stage exists because simulation has a measured blind spot: an
  effective FIFO depth of 7 instead of 8 passes 13/13 patterns with 0.0%
  throughput change, and `a_no_false_stall` rejects it in under a second.
  A formal `skip` (no `sby`) does not block a verdict; a formal `fail` does.
- **Mutation coverage** — injects one plausible fault at a time and runs the
  real gate on each. A pass rate says the design agrees with the golden model on
  the inputs someone wrote down; this says whether the suite would *notice* if
  the design were wrong. ~10s per mutant. A **survivor is a concrete edit to
  `rtl/gamma.v` that every check in this repository accepts** — that is the
  finding, not the percentage.
- **Run loop** — generates a candidate for your goal, gates it, and on rejection
  feeds the *exact* mismatch (pattern, pixel index, RTL value vs golden value)
  into the next attempt.

Outcomes are deliberately not a boolean:

| Outcome | Meaning |
|---|---|
| `PROVEN_CHANGE` | a **changed** RTL is bit-exact against the golden model |
| `ORACLE_CONFLICT` | every attempt that implemented the goal was rejected on values — the goal contradicts the golden model |
| `NO_CHANGE` | it ended at the committed RTL; the goal was not implemented |
| `EXHAUSTED` | budget spent with no proven candidate |

`ORACLE_CONFLICT` matters: if the new behaviour is genuinely wanted, the **golden
model must change first**. The RTL is never the place to redefine correctness.

Nothing is written to `rtl/`. A proven candidate lands in `build/improve/` and
**Apply** promotes it — re-proving it first, and backing up the current RTL.

### Style and coverage
Not views — endpoints, because they are measurements you run rather than screens
you watch. `GET /style` reports house-style findings (folded into the `design`
gate stage) and `GET /coverage` reports line coverage. In both, the number to
act on is the one that names a line: a style finding cites the convention it
enforces, and coverage's `never-executed` is the signal, not the percentage.

### Knowledge
What the agent is given as grounding, with the retrieval scores. Type a question
and press **Retrieve**.

This exists for a specific debugging reason: when an agent answer is wrong, you
need to know whether **retrieval missed** or **the model erred** — different
bugs with different fixes. Search here with the same question and look.

Retrieval is lexical (BM25), not embeddings, on purpose: the queries are
identifiers like `in_ready` and `FIFO_DEPTH`, and vector similarity blurs exactly
those. Korean questions are bridged by a domain glossary.

### Assistant
**Plan** turns a spec change into tagged steps. The full `docs/UARCH.md` is sent
as the input — you edit only the **CHANGED** delta. Each step is tagged
`NEW` / `MODIFIED` / `UNCHANGED` so an incremental regeneration touches only what
moved.

**Ask** is the RTL assistant. Every reply carries the passages that grounded it —
expand *"grounded in N passages"* to check the answer against its sources.

Write in Korean and you get Korean back.

---

## Common tasks

**Prove the design still works.**
Toolbar ▸ Run sign-off. Or `./scripts/run_3way.sh`.

**Investigate a handshake question.**
Waveform ▸ Re-simulate, then place the cursor at the moment of interest and read
`in_ready`, `count`, `out_valid` together.

**Find where a signal is driven.**
Schematic, click the cell; Properties gives you `rtl/gamma.v:<line>`.

**Change precision or FIFO depth.**
This is the Δ-propagation drill — three files must move together. See
`docs/UARCH.md` §7. Then re-run sign-off: the hashes must be unchanged for a
depth change (timing-only) and *will* change for a precision change.

**Decide what to work on next.**
Improve ▸ read the evidence gaps. They are ranked by how much they would change
what the scoreboard actually proves.

**Check what the agent knows about something.**
Knowledge ▸ type the question ▸ Retrieve. If nothing matches, the agent would be
answering from pinned context alone — consider adding a source.

**Hand a failure to someone.**
Transcript ▸ set the threshold to `W` ▸ Copy.

---

## When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| Assistant returns 503 | no gateway key | set `HERMES_GATEWAY_API_KEY` in `.env` |
| `skills 2/6` in the toolbar | the serving profile lacks skills | `python scripts/sync_hermes_skills.py` |
| status bar shows an unexpected profile | another agent took port 8643 | `lsof -nP -iTCP:8643 -sTCP:LISTEN` |
| Schematic says unavailable | yosys not on PATH | install yosys |
| Waveform says no dump | never traced | Re-simulate, or `make -C tb WAVES=1` |
| SystemC column all skipped | no `build/sc_out.txt` | build the SystemC sim (see README) |
| Scoreboard looks stale | backend unreachable | it fell back to `public/results.json`; check the server |
| Panes look broken | a stored pane size | View ▸ Reset layout |
| cocotb fails with a Python error | `PYTHONHOME` poisoning | activate the venv before `make` |

---

## Command-line equivalents

```sh
./scripts/run_3way.sh                   # full regression
python -m pytest tests/ -q              # L0 unit tests, no simulator
cd tb && make                           # L1+L2, verilator
cd tb && make SIM=icarus                # 4-state cross-check
cd tb && make WAVES=1                   # with VCD
cd tb && make TESTCASE=test_lut_reload  # one test
BP_PROFILE=full make -C tb              # every pattern x profile (nightly)
scripts/build_systemc.sh                # the third model

sby -f formal/gamma.sby prove           # control path, unbounded (k-induction)
sby -f formal/gamma.sby prove_sync      # the same, with LUT_SYNC_READ=1
sby -f formal/gamma.sby datapath        # values, bounded
sby -f formal/gamma.sby cover           # reachability (the proof is not vacuous)
sby -f formal/gamma.sby bmc             # bounded, for a counterexample trace

curl localhost:8012/api/verification     # scoreboard
curl localhost:8012/api/style            # house style
curl localhost:8012/api/coverage         # line coverage
curl localhost:8012/api/skills           # what the agent can load
curl "localhost:8012/api/kb/search?q=in_ready"   # what it would be told
python scripts/sync_hermes_skills.py --list      # skill install state
cd frontend && npm run check:responsive          # layout gate
```

---

## Further reading

- **[`README.md`](../README.md)** — why the project exists
- **[`docs/UARCH.md`](UARCH.md)** — the microarchitecture specification
- **[`TESTPLAN.md`](../TESTPLAN.md)** — test layers, coverage rationale, and the
  known gaps, stated plainly
- **[`CLAUDE.md`](../CLAUDE.md)** — repository conventions for contributors
