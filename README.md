# Gamma 3-way Scoreboard Skeleton

Pilot for Python golden ↔ SystemC ↔ RTL bit-exact verification.

## Layout

```
golden/gamma_golden.py     numpy reference (single source of truth)
rtl/gamma.v                Verilog DUT, 1-cycle latency, ready/valid
systemc/gamma_sc.{h,cpp}   cycle-accurate SystemC mirror
systemc/sim_main.cpp       standalone driver -> sc_out.txt
tb/test_gamma.py           cocotb 3-way scoreboard + directed protocol tests
tb/stimulus.py             colorbar / gradient / random / edge / sweep / ...
tb/test_set.py             canonical pattern registry + per-channel LUTs
tb/Makefile                cocotb + Verilator
tests/                     pytest unit tests (golden model, stimulus, test set)
scripts/gen_sc_inputs.py   produces stim.txt, lut.txt for SystemC sim
scripts/run_3way.sh        end-to-end driver (unit tests + SC + RTL)
TESTPLAN.md                test-set documentation (L0/L1/L2 layers)
```

## Prerequisites

- Python 3.10+, `pip install -r requirements.txt` (numpy, cocotb<2.0, pytest)
- Verilator >= 5.0
- SystemC 2.3.x (set `SYSTEMC_HOME`) — optional; SC compare is skipped if absent
- Optional: `pip install pyuvm` for richer scoreboard later

## Build & Run

```sh
# 0. One-time setup (cocotb needs an activated venv)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Build the standalone SystemC sim (once, optional)
g++ -std=c++17 -I$SYSTEMC_HOME/include -L$SYSTEMC_HOME/lib \
    systemc/sim_main.cpp systemc/gamma_sc.cpp \
    -lsystemc -o build/gamma_sc_sim

# 2. Run the full regression
./scripts/run_3way.sh

# Or run the layers individually:
python3 -m pytest tests/ -q     # L0: unit tests, no simulator needed
cd tb && make                   # L1+L2: directed + 3-way RTL tests
```

`run_3way.sh` does:
0. pytest unit tests gate the golden model, stimulus, and test-set integrity
1. Python writes `build/lut.txt` and `build/stim.txt`
2. SystemC sim consumes them, dumps `build/sc_out.txt`
3. cocotb drives the same stimulus into the Verilog DUT, then per-pattern compares Python golden vs RTL vs SystemC

See `TESTPLAN.md` for the full test-set description (patterns, directed
tests, coverage rationale, known gaps).

## Scoreboard contract

Per pattern (registry in `tb/test_set.py`: `edge_cases`, `colorbar`,
`gradient`, `random_seed0`, `lut_sweep`, `channel_isolation`, `checkerboard`,
`near_extremes` — order is the sc_out.txt contract, append only):
- `Python golden` computed in-process from numpy LUT.
- `RTL out` collected on `out_valid && out_ready`.
- `SystemC out` read from `sc_out.txt` line-by-line.
- Pass = bit-exact across all three. Mismatch reports first index + values + total mismatch count.
- Frame SHA-256 logged for traceability across regression runs.

## Extending

- **Backpressure**: randomize `out_ready` in `test_gamma.py` to exercise stalls.
- **LUT depth / precision change**: bump `LUT_SIZE`/`PIXEL_W` in `gamma_golden.py`, `gamma.v`, `gamma_sc.h` together — this is the Δ-propagation drill.
- **Per-stage tap-out**: when chaining CSC → gamma → dither, expose intermediate ports and add one scoreboard per stage.
- **Coverage**: replace `random_frame(seed=0)` with `pyuvm` constrained-random sequences.
- **MIPI / TCON wrapper**: wrap this DUT in the upstream pixel router and re-run; same scoreboard hashes must hold.
