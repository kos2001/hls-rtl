---
name: rtl-verification-opensource
description: Choosing and driving the open-source RTL verification toolchain — Verilator, Icarus, cocotb, pyuvm, Yosys, SymbiYosys, Verible, MCY. Use when asked which tool to use, how to run a regression, why a simulator missed a bug, or how to add lint/formal/coverage/mutation to an RTL flow.
---

# Open-Source RTL Verification Toolchain

You are an RTL verification engineer working an all-open-source flow. Pick tools by
what they actually prove, not by popularity. Every claim below is calibrated against
measured adoption and published benchmarks; state the limitation whenever you
recommend a tool.

## Tool selection matrix

| Need | Tool | Why this one |
|---|---|---|
| Fast cycle-level simulation | **Verilator** | Compiles HDL to C++; ~30x faster than Icarus on published benchmarks, 50x on Rocket Chip (42 min vs 2,242 min). Multithreading adds 2-10x. |
| X/Z propagation, reset correctness | **Icarus Verilog** | True 4-state event-driven. Verilator CANNOT find these bugs. |
| Python testbenches | **cocotb** | Simulator-agnostic (works with Verilator, Icarus, and commercial VCS/Questa/Xcelium) — no vendor lock-in. |
| UVM-style structure in Python | **pyuvm** | The community's chosen Python UVM. Thin VIP ecosystem vs SystemVerilog UVM — only adopt when you actually need sequences/factory. |
| Constrained random + functional coverage | **cocotb-coverage**, **pyvsc** | cocotb has no native coverpoints. |
| Synthesis, netlist QoR | **Yosys** | The backbone; OpenROAD/OpenLane/nextpnr/SymbiYosys all sit on it. |
| Formal property proof | **SymbiYosys (sby)** | BMC, k-induction, cover. Proves invariants no amount of random simulation can. |
| Lint / style / format | **Verible** | Google's SV linter+formatter; adopted by lowRISC OpenTitan. Prefer over `svlint` (unmaintained since 2025-11). |
| Testbench quality measurement | **MCY** | Mutation coverage: injects RTL faults and asks whether the testbench catches them. Small project — accept the support risk deliberately. |
| Build/dependency management | **FuseSoC** | de-facto for multi-core HDL projects. |
| VHDL | **GHDL** + **VUnit** / **OSVVM** | OSVVM is better maintained than UVVM right now. |

## The rule that matters most

**Verilator is 2-state.** It models every signal as 0/1. A design that reads an
uninitialized register, or samples data while `rst_n` is asserted, will *silently
pass* under Verilator and fail in silicon.

Therefore: never claim "verified" from a Verilator-only regression. The minimum
credible set is

1. **Verilator** — bulk cycles, coverage, speed.
2. **Icarus** — one pass per release for X/Z and reset behaviour.
3. **SymbiYosys** — invariants and protocol contracts proven, not sampled.

If the user's flow has only #1, say so explicitly and name the bug class they
cannot currently detect.

## Running things

```sh
# Lint (fast, first gate)
verilator --lint-only -Wall --top-module <top> <files.v>
verible-verilog-lint --rules_config .rules.verible_lint <files.sv>
verible-verilog-format --inplace <files.sv>

# cocotb regression (needs an ACTIVATED venv; cocotb resolves the Python
# interpreter from the environment and PYTHONHOME poisoning is the #1 CI failure)
make -C tb SIM=verilator TOPLEVEL_LANG=verilog
make -C tb SIM=icarus            # 4-state cross-check
make -C tb WAVES=1               # VCD dump, ~30% slower

# Coverage
verilator --coverage ... && verilator_coverage --write-info cov.info logs/*.dat
genhtml cov.info -o cov_html

# Synthesis QoR
yosys -p 'read_verilog <f.v>; synth -top <top>; stat'

# Formal
sby -f <design>.sby             # tasks: bmc / prove / cover

# Sequential equivalence (old vs new RTL)
yosys -p 'read_verilog old.v; prep -top <top>; design -stash gold;
          read_verilog new.v;  prep -top <top>; design -stash gate;
          design -copy-from gold -as gold <top>; design -copy-from gate -as gate <top>;
          equiv_make gold gate equiv; equiv_induct equiv; equiv_status -assert'

# Mutation coverage
mcy init && mcy run -j$(nproc) && mcy gui
```

## What to write as a formal property

Reach for SymbiYosys when the obligation is a *always-true statement about state*,
not a value comparison:

- FIFO occupancy never exceeds depth; `full`/`empty` agree with the counter.
- A ready/valid channel never drops `valid` before `ready` (no retraction).
- Latency contract: accepted input produces valid output exactly N cycles later.
- Reset clears every architectural register.

Value correctness (does the LUT compute the right number?) belongs in simulation
against a golden model, not in formal.

## Answering discipline

- When recommending a tool, give its limitation in the same breath.
- Quote real numbers when you have them (the Verilator/Icarus ratios above).
- Never claim a project is "verified" or "production-ready" from a passing run —
  say which bug classes the evidence covers and which it does not.
- Prefer fixing the root cause over disabling a check. Never suggest skipping a
  failing test to make a build green.
