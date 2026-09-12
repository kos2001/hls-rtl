---
name: gamma-bitexact-verification
description: The gamma pixel-core 3-way bit-exact contract (Python golden / SystemC / Verilog RTL), its handshake and latency guarantees, the append-only test set, backpressure profiles, and the sign-off ladder. Use for any question about the gamma DUT, its scoreboard, changing precision or FIFO depth, or interpreting a verification/QoR/sign-off result.
---

# Gamma Core — Bit-Exact Verification Contract

The design under verification is a gamma-correction pixel core. Three independent
models must produce **identical** output for the same stimulus and LUTs, proven per
pattern by SHA-256 frame hashes.

## The three models

| Model | File | Role |
|---|---|---|
| Python golden | `golden/gamma_golden.py` | numpy reference — **the single source of truth** |
| SystemC | `systemc/gamma_sc.{h,cpp}` | cycle-accurate mirror (HLS-side representation) |
| Verilog RTL | `rtl/gamma.v` | the synthesizable DUT |

The golden model defines the expected hashes. SystemC and RTL are *candidates* proven
against it. Never invert this: if RTL and golden disagree, the RTL is wrong until
proven otherwise.

## DUT contract — do not restate these wrong

- 1 pixel/cycle, ready/valid handshake, per-channel LUT.
- Parameterizable elastic **FIFO**, `FIFO_DEPTH` default 8.
- `in_ready = (count != FIFO_DEPTH)` — **registered occupancy only**. There is
  deliberately *no* combinational `out_ready -> in_ready` path.
- **1-cycle latency** from accepted input to valid output. The FIFO only fills
  during a downstream stall.
- Async **active-low** reset clearing pointers and occupancy.
- `gamma.v` asserts `LUT_DEPTH == 2**PIXEL_W` at elaboration.

## Verilog-2001 on purpose

`rtl/gamma.v` is intentionally portable Verilog-2001 (`reg`/`wire`, `always @`).
The cocotb flow runs under `TOPLEVEL_LANG=verilog`.

**Do not "modernize" it to SystemVerilog** (`logic`, `always_ff`, `always_comb`,
interfaces) unless the user explicitly asks and accepts the flow change. Generic
SystemVerilog style advice does not override this. The QoR analyzer
(`api/rtl_qor.py`) is calibrated for Verilog-2001 and does not penalize `reg`/`wire`.

## The Δ-propagation drill

Changing precision or depth touches **three files that must stay aligned**. Bump
`LUT_SIZE` / `PIXEL_W` / `LUT_DEPTH` together in:

1. `golden/gamma_golden.py`
2. `rtl/gamma.v`
3. `systemc/gamma_sc.h`

Miss one and the scoreboard breaks. Always list all three when proposing such a change.

## Test set is append-only

The canonical patterns and per-channel LUTs live in `tb/test_set.py`.
`build/sc_out.txt` is consumed **sequentially**, so pattern order is a contract —
**only append** new patterns, never insert or reorder.

Per-channel gammas are deliberately distinct (R=2.2, G=1.8, B=2.8) so a swapped or
crossed channel cannot alias into a bit-exact pass. Do not "simplify" them to one value.

## Backpressure profiles

Backpressure changes **ordering, not values** — bit-exactness must still hold under
every profile.

- `BP_PROFILE=split` (default) — data coverage, then protocol coverage.
- `BP_PROFILE=full` — every pattern x every profile (nightly).
- `BP_PROFILE=single` — one profile from `BP_SEED`, `BP_IN_STALL`, `BP_OUT_STALL`,
  `BP_IN_BURST`, `BP_OUT_BURST`.
- `GAMMA=<float>` overrides all three channels (legacy single-gamma flow).

If `build/sc_out.txt` is absent the SystemC compare is **skipped, not failed**; the
RTL-vs-golden comparison still gates.

## Commands

```sh
./scripts/run_3way.sh                     # full regression
python -m pytest tests/ -q                # L0 unit tests, no simulator
cd tb && make                             # L1+L2 directed + 3-way (verilator)
cd tb && make TESTCASE=test_single_pixel_latency
cd tb && make WAVES=1
```

cocotb needs an **activated venv** — `PYTHONHOME` poisoning from a system Python is
the known CI failure mode here.

## Sign-off ladder

`POST /signoff` runs **lint -> design -> synthesize -> simulate**, where `simulate`
is the real cocotb 3-way regression (`make -C tb`), not a mock. Verdicts:

- `SIGNED_OFF` — every gating stage passed.
- `CONDITIONAL` — non-gating issues remain.
- `REJECTED` — a gating stage failed.

A stage marked `skip` is missing evidence, not a pass. Say so when reporting.

## Reading a result honestly

- "13/13 patterns bit-exact" means the RTL matches golden **on those patterns under
  the profiles that ran**. It is not a proof of correctness for all inputs.
- The regression runs under Verilator (2-state), so it cannot detect X-propagation
  or reset-initialization bugs. Name this gap rather than implying full coverage.
- See `TESTPLAN.md` for the L0/L1/L2 layer rationale and the recorded known gaps.
