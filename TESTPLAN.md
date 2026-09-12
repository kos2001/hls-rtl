# Validation Test Plan

Three-layer test set for the gamma-correction DUT. Each layer runs
independently; together they form the regression gate.

## L0 — Golden model & test-set unit tests (`tests/`, pytest)

No simulator required. Locks down the reference the other layers compare against.

| Test file | What it verifies |
|---|---|
| `test_golden.py` | LUT endpoints pinned (0→0, 255→255), monotonicity, 8-bit range, gamma=1.0 identity, frozen reference anchors, `apply_gamma` vs naive per-pixel lookup, per-channel routing, `frame_hash` determinism/sensitivity |
| `test_stimulus.py` | Every pattern: uint8 RGB, deterministic; per-pattern coverage claims (gradient hits all 256 codes, `lut_sweep` reads each LUT entry exactly once per channel, decorrelated channels, checkerboard alternates every neighbor, `near_extremes` stays on boundary values) |
| `test_test_set.py` | Pattern order frozen (sc_out.txt is consumed positionally), full per-channel LUT coverage across the set, per-channel-distinct default LUTs, `GAMMA` env override, `gen_sc_inputs.py` output bit-identical to the registry |

Run: `python3 -m pytest tests/ -q`

## L1 — Directed RTL protocol tests (`tb/test_gamma.py`, cocotb + Verilator)

| Test | What it verifies |
|---|---|
| `test_reset_state` | After reset: `out_valid=0`, `in_ready=1` (no stale output, ready to accept) |
| `test_single_pixel_latency` | Exactly 1-cycle accept→output latency, bit-exact value, `out_valid` drops after consumption |
| `test_full_rate_throughput` | 1 pixel/cycle sustained with no stalls: `in_ready` never drops, no output bubbles |
| `test_lut_reload` | Runtime LUT reload: identity pass-through, then gamma curve, both bit-exact |

## L2 — 3-way randomized/directed scoreboard (`test_gamma_3way`)

Python golden ↔ SystemC ↔ RTL bit-exact compare across 8 patterns and 5
backpressure profiles (`no_bp`, `out_only`, `in_only`, `both_light`,
`both_heavy`).

### Run modes (`BP_PROFILE` env)

| Mode | Behavior | Use |
|---|---|---|
| `split` (default) | Phase 1: all 8 patterns @ no_bp (data + LUT coverage + SC compare). Phase 2: `gradient`+`checkerboard` × 4 stall profiles (protocol coverage). | CI / dev loop |
| `full` | Exhaustive 8 patterns × 5 profiles cross-product | Nightly |
| `single` | One env-defined profile across all patterns | Debug a stall case |

Rationale: backpressure changes pixel *ordering*, not *values*, so the full
cross-product is largely redundant. Splitting data coverage from protocol
coverage cut `test_gamma_3way` sim time **805 µs → 426 µs (−47%)** and the
incremental regression wall-clock **5.5 s → 4.0 s (−27%)** with no loss of
coverage (every value path still runs at no_bp; every stall profile still runs
against varied data).

Patterns (order is the sc_out.txt contract — append only):

| Pattern | Target |
|---|---|
| `edge_cases` | Min/max/mixed corner pixels |
| `colorbar` | Saturated primaries/secondaries |
| `gradient` | All 256 input codes, correlated channels |
| `random_seed0` | Unconstrained random |
| `lut_sweep` | Every LUT entry of every channel exactly once, channels decorrelated (offset +85/+170) — catches channel swap/crosstalk |
| `channel_isolation` | One channel ramps while others sit at 0 — isolates per-channel routing |
| `checkerboard` | 0↔255 alternation every pixel — max datapath toggling |
| `near_extremes` | Random biased to codes {0,1,2,127,128,129,253,254,255} where gamma quantization steps cluster |

LUTs default to **distinct per-channel gammas** (R=2.2, G=1.8, B=2.8) so a
swapped/crossed channel cannot alias to a pass. `GAMMA=<float>` env restores
the legacy single-gamma flow. `tb/test_set.py` is the single registry shared
by cocotb and `scripts/gen_sc_inputs.py`.

## Throughput instrumentation & performance guard

`run_pattern` now reports `cyc/px` for every pattern/profile and **asserts
full-rate throughput** under no_bp (`cycles <= pixels + 3`). This is a
performance-regression gate, not just a log line — verified by injecting an
every-other-cycle accept bug into `in_ready`, which the guard caught
(48 cyc vs ≤27 expected for 24 px).

### Measured DUT throughput (cyc/px, lower is better)

With the **FIFO_DEPTH=8 elastic FIFO** in `rtl/gamma.v`
(`in_ready = (count != FIFO_DEPTH)`, registered occupancy only — no
combinational out_ready→in_ready path):

| Profile | gradient | checkerboard | skid-2 | no buffer | ideal* |
|---|---|---|---|---|---|
| no_bp | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| out_only (0.3 stall) | 1.74 | 1.69 | 1.74 / 1.69 | 1.74 / 1.69 | ~1.43 |
| in_only (0.3 stall) | 2.49 | 2.59 | 2.49 / 2.59 | 2.49 / 2.59 | ~1.43 |
| both_light (0.15/0.15) | **1.49** | **1.47** | 1.69 / 1.64 | — | — |
| both_heavy (0.5/0.5) | **5.59** | **5.36** | 6.82 / 7.11 | 8.34 / 8.58 | ~2.0 |

\* ideal = throughput a fully-elastic (infinite-buffer) datapath could sustain
at that stall probability.

### FIFO_DEPTH sweep (2026-07-02, `EXTRA_ARGS="-GFIFO_DEPTH=N"`, all depths 5/5 pass, 0 mismatches)

| both_heavy (grad/chk) | D=2 | D=4 | D=8 | D=16 | D=32 |
|---|---|---|---|---|---|
| cyc/px | 6.82/7.11 | 5.87/5.48 | **5.59/5.36** | 5.57/5.44 | 5.57/5.44 |
| flops | 6196 | 6247 | 6346 | 6541 | 6928 |

Knee at **D=8**: 16/32 buy ≤0.3% on gradient (checkerboard slightly worse —
seed-alignment noise, deeper FIFOs shift accept timing vs the RNG stall
sequence) for +195/+582 flops. `out_only`/`in_only` identical at every depth
(port-bound). Default stays FIFO_DEPTH=8.

### Other performance levers evaluated (2026-07-02)

- **`LUT_SYNC_READ=1` (applied, opt-in)**: registered LUT read — the classic
  BRAM-inference pattern, removing the combinational LUT→FIFO path the EDA
  review flagged as the Fmax/area bottleneck on FPGA. Cost: accept→out latency
  becomes 2 cycles, so it is a synthesis-time knob, default 0 (the 1-cycle
  contract). Verified bit-exact + full-rate via
  `EXTRA_ARGS="-GLUT_SYNC_READ=1" TESTCASE=test_gamma_3way make`.
- **Full-slot reclaim (`in_ready = ~full | pop`) — rejected on measurement**:
  identical cyc/px on every profile at D=8 (the FIFO is rarely exactly-full at
  a pop edge), and it re-introduces the combinational out_ready→in_ready path
  the FIFO design deliberately removed.
- **Multi-lane (N px/cycle)**: the remaining big lever; changes the stream
  interface and all three models — needs its own contract sign-off.

**Finding:** buffering helps exactly where theory says it can — decoupling
simultaneous in/out stalls. Cumulative gains vs the unbuffered design:
`both_heavy` −33%/−37% (8.34→5.59 / 8.58→5.36), `both_light` −12%. The 8-deep
FIFO absorbs the profiles' burst stalls (len 4–6) that overflowed the 2-deep
skid. `out_only`/`in_only` are port-bound and correctly unchanged — no buffer
depth can raise throughput past the stalling port. The remaining gap to `ideal`
at both_heavy is burst-correlation (long overlapping in+out bursts drain any
finite buffer); closing it further costs exponentially more depth for
diminishing returns. Contract preserved: **1-cycle latency** (the FIFO only
fills during downstream stalls), `test_single_pixel_latency` /
`test_full_rate_throughput` pass unchanged, all 13 patterns bit-exact. Cost:
+177 flops (6169→6346, the FIFO storage + pointers).

## Line coverage (`GET /coverage`)

Verilator-instrumented run, annotated. **`never-executed` is the number that
matters**; `partial` frequently reflects how Verilator attributes branch points
to declaration lines, and the `translate_off` elaboration guards are exempt by
source range — requiring them would mean the only route to 100% is to break the
design.

It found one genuinely unreached line: the `default:` arm of the `lut_ch`
decode, i.e. the reserved `2'b11` encoding. The RTL documents "reserved encoding
-> no write" as a contract and nothing checked it. `test_lut_reserved_encoding`
now does, and it was verified against a decoder that aliases the reserved code
onto channel R — caught, with the poison value visible in the failure.

## Mutation coverage (automated — `api/mutate.py`)

48 single-fault mutants over seven fault classes (relational, arithmetic,
boolean, off-by-one, stuck-at, dropped-update, channel-cross), each run through
the full sign-off gate. **100% caught**, no survivors:

| caught by | count |
|---|---|
| simulate | 25 |
| configs (`LUT_SYNC_READ=1`) | 10 |
| lint | 9 |
| formal | 2 |
| synthesize | 1 |
| 4-state (Icarus) | 1 |

Every stage earns its place: `formal` and `4state` each catch faults nothing
before them sees, and `configs` accounts for ten.

Every survivor so far has been in the `LUT_SYNC_READ=1` generate branch, which
the default elaboration never builds — first three of them, which the `configs`
stage now covers by re-running the bit-exact comparison in that mode; then one
more, an occupancy off-by-one that `configs` could not see because depth is
timing-only and that stage compares values. The formal tasks now run in that
configuration too (`prove_sync`), which closes it.

Re-run after changing the RTL. A survivor is an edit that every check in this
repository accepts.

## Mutation checks (done manually, 2026-06-12/13)

- **Channel swap**: swapping `lut_r_mem`/`lut_b_mem` reads is caught by
  `test_single_pixel_latency` and the 3-way compare. Under the previous
  identical-LUT setup this mutation passed silently.
- **Throughput regression**: an every-other-cycle `in_ready` bug is caught by
  the no_bp throughput guard in `run_pattern`.

## Known gaps / next steps

- **Elastic buffering**: ✅ done in two steps — 2-deep skid (−18% both_heavy),
  then a parameterizable `FIFO_DEPTH` elastic FIFO (default 8) absorbing the
  burst (len 4–6) stalls: `both_heavy` 8.34→5.59 cyc/px (−33%) cumulative,
  1-cycle latency contract intact. Depth is a synthesis-time knob; remaining
  gap to ideal is burst-correlation, diminishing returns beyond depth ~8.
- SystemC leg not exercised on machines without `SYSTEMC_HOME` (compare is
  skipped with a warning; RTL-vs-golden still gates).
- No X-propagation checks (Verilator is 2-state; needs an event-driven sim).
- LUT write during in-flight pixel (`lut_we` racing the stream) is untested —
  define the intended semantics first.
- No functional coverage collection; `BP_SEED` sweeps are manual.

## Test-runtime tuning summary

| Change | Effect |
|---|---|
| VCD trace opt-in (`make WAVES=1`) | Avoids a 6.7 MB dump + ~30% sim cost on every run |
| Verilator `-O3` | Faster compiled model, negligible build cost |
| Merged ready-driver + collector into one `sink` coroutine | Halves sink-side scheduler wakeups per cycle |
| `split` run mode (data vs protocol phases) | `test_gamma_3way` −47% sim time; regression −27% wall-clock |
