# gamma — Microarchitecture Specification

Per-channel gamma-correction pixel core. 1 pixel/cycle, ready/valid, 8b→8b.

This document is the **design input** of the flow, not a description written
after the fact: `POST /plan` takes it (plus the golden algorithm) and emits a
step-by-step implementation plan, and it is indexed into the knowledge base that
grounds every agent answer. Keep it true — an agent that reads a stale uArch
will confidently plan against a design that does not exist.

- **Reference implementation**: `golden/gamma_golden.py` (authoritative values)
- **RTL**: `rtl/gamma.v` (Verilog-2001, deliberately)
- **Cycle-accurate model**: `systemc/gamma_sc.{h,cpp}`

---

## 1. Function

For each pixel, each channel is independently mapped through its own 256-entry
lookup table:

```
out_r = lut_r[in_r]
out_g = lut_g[in_g]
out_b = lut_b[in_b]
```

The LUT content is not the core's concern — it is written at runtime. The golden
model builds it as `round((x/255)^(1/γ) * 255)` with **distinct per-channel γ
(R=2.2, G=1.8, B=2.8)**. That asymmetry is a verification decision, not a
functional one: with identical LUTs a swapped channel produces identical output
and a crossed-channel bug passes silently.

The core is a **pure mapping plus elasticity**. It never reorders, never drops,
never duplicates, and never alters a value. Backpressure changes *when* a pixel
appears, never *what* it is or *what order* pixels come in. This is the property
the 3-way scoreboard checks.

---

## 2. Interface

### 2.1 Parameters

| Parameter | Default | Meaning | Constraint |
|---|---|---|---|
| `PIXEL_W` | 8 | Bits per channel, in and out | — |
| `LUT_DEPTH` | 256 | LUT entries per channel | **must equal `2**PIXEL_W`** (elaboration-checked) |
| `FIFO_DEPTH` | 8 | Elastic buffer depth | **≥ 2** (elaboration-checked) |
| `LUT_SYNC_READ` | 0 | 0 = combinational LUT read (1-cycle contract); 1 = registered read (2-cycle, BRAM-inferable) | 0 or 1 |

Both constraints are enforced by `$error` in a `translate_off` `initial` block,
so an illegal configuration fails at elaboration rather than at the scoreboard.

### 2.2 Ports

| Port | Dir | Width | Notes |
|---|---|---|---|
| `clk` | in | 1 | single clock domain; no CDC inside |
| `rst_n` | in | 1 | **asynchronous, active low** |
| `in_valid` | in | 1 | pixel stream in |
| `in_ready` | out | 1 | **function of registered state only** |
| `in_r/g/b` | in | `PIXEL_W` | |
| `out_valid` | out | 1 | pixel stream out |
| `out_ready` | in | 1 | |
| `out_r/g/b` | out | `PIXEL_W` | |
| `lut_we` | in | 1 | LUT write port |
| `lut_ch` | in | 2 | `00`=R, `01`=G, `10`=B, `11`=reserved (no write) |
| `lut_addr` | in | `$clog2(LUT_DEPTH)` | |
| `lut_wdata` | in | `PIXEL_W` | |

### 2.3 Handshake rules

- A transfer happens on a rising edge where `valid && ready`.
- Once asserted, `valid` is held until the transfer completes (no retraction).
- `in_ready` **must not** depend combinationally on `out_ready` — see §4.2.
- The LUT write port has no handshake: one channel/address per cycle, accepted
  whenever `lut_we` is high. Writing a LUT entry while pixels are in flight is
  legal but the crossover point is not specified — quiesce the stream first.
  `test_lut_reload` exercises the supported sequence.

---

## 3. Block diagram

```
                 lut_we / lut_ch / lut_addr / lut_wdata
                                  │
                                  ▼
                        ┌───────────────────┐
                        │  lut_r_mem [256]  │
                        │  lut_g_mem [256]  │   sync write, 1 ch/cycle
                        │  lut_b_mem [256]  │
                        └─────────┬─────────┘
   in_valid ──┐                   │ read @ in_r/g/b
   in_r/g/b ──┼──────────────────►│   (comb, or registered if LUT_SYNC_READ=1)
              │                   ▼
              │        ┌─────────────────────┐
              │        │   fifo_mem[DEPTH]   │  3*PIXEL_W wide
   in_ready ◄─┤        │   wr_ptr ──►        │  circular, sync write
              │        │        ◄── rd_ptr   │
              │        │   count (occupancy) │
              │        └──────────┬──────────┘
              │                   │ head, combinational from registered ptr
              │                   ▼
   in_ready = (count != FIFO_DEPTH)      out_r/g/b
   out_valid = (count != 0)              out_ready ──► pop
```

Three separate LUT memories rather than one wide one: each is indexed by a
different channel's pixel value in the same cycle, so they are three concurrent
reads, not one.

---

## 4. Control

### 4.1 Occupancy

One registered counter is the single source of truth for both flags:

```verilog
push = in_valid  & in_ready
pop  = out_valid & out_ready
count <= count + push - pop        // async reset clears to 0
```

`wr_ptr` and `rd_ptr` advance independently on `push`/`pop`, wrapping at
`FIFO_DEPTH-1`. A separate counter (rather than deriving full/empty from pointer
equality) is what makes a full FIFO distinguishable from an empty one without a
wrap bit.

### 4.2 Why `in_ready` is registered-only

```verilog
assign in_ready  = (count != FIFO_DEPTH);   // registered state
assign out_valid = (count != 0);            // registered state
```

Neither flag reads `out_ready` or `in_valid`. **There is deliberately no
combinational path from `out_ready` to `in_ready`.** In a pipeline of these
cores, such a path concatenates: every stage's `ready` feeds the previous
stage's `ready` in the same cycle, and the critical path grows with pipeline
depth ("ready ripple"). Paying one FIFO entry to break it keeps the timing
closure of a chain independent of its length.

The cost is that the FIFO must be able to accept a pixel that was already
committed, which is why `LUT_SYNC_READ=1` reserves the in-flight stage-1 entry:

```verilog
assign in_ready = ((count + s1_valid) != FIFO_DEPTH);
```

### 4.3 Reset

Asynchronous, active low. It clears `rd_ptr`, `wr_ptr`, `count`, and (in sync-read
mode) `s1_valid`.

`fifo_mem` and the LUT memories are **not** reset — deliberately. Resetting a
256×3 entry memory array costs flops or a reset state machine for no benefit:
`out_valid` is 0 while `count` is 0, so uninitialised storage is never presented
as valid data. `test_reset_state` gates this.

> **Known gap.** The regression runs under Verilator, which is 2-state. It
> therefore cannot prove that the unreset memories are never *read* as X. Run
> `make -C tb SIM=icarus` for a 4-state check before claiming that property.

---

## 5. Timing

### 5.1 Latency

| Mode | accept → `out_valid` | Path |
|---|---|---|
| `LUT_SYNC_READ=0` (default) | **1 cycle** | LUT read is combinational; write into FIFO at the accept edge, head visible at T+1 |
| `LUT_SYNC_READ=1` | **2 cycles** | LUT read captured in a register at the accept edge, written into the FIFO one cycle later |

Values and ordering are identical in both modes — the difference is latency
only, verified bit-exact with `EXTRA_ARGS="-GLUT_SYNC_READ=1"`.

The FIFO adds latency **only while the downstream is stalled**. With
`out_ready` continuously high, occupancy never exceeds 1.

### 5.2 Throughput

1 pixel/cycle sustained when neither side stalls. `run_pattern` asserts this as
a gate, not a log line: `cycles <= pixels + 3` under `no_bp`.

Measured `cyc/px` (lower is better), from `TESTPLAN.md`:

| Profile | FIFO_DEPTH=8 | skid-2 | no buffer | elastic ideal |
|---|---|---|---|---|
| `no_bp` | 1.00 | 1.00 | 1.00 | 1.00 |
| `both_light` (0.15/0.15) | **1.49** | 1.69 | — | — |
| `both_heavy` (0.5/0.5) | **5.59** | 6.82 | 8.34 | ~2.0 |
| `out_only` (0.3) | 1.74 | 1.74 | 1.74 | ~1.43 |
| `in_only` (0.3) | 2.49 | 2.49 | 2.49 | ~1.43 |

`out_only`/`in_only` are identical at every depth because they are port-bound:
buffering cannot manufacture a pixel the source did not offer.

### 5.3 Why `FIFO_DEPTH = 8`

A 2-deep skid buffer absorbs single-cycle stalls. The test profiles stall in
**bursts of 4-6 cycles**, which overflow it — that is why `both_heavy` costs
6.82 cyc/px with a skid but 5.59 with the FIFO.

Depth sweep (all depths pass bit-exact, `both_heavy` gradient/checkerboard):

| | D=2 | D=4 | **D=8** | D=16 | D=32 |
|---|---|---|---|---|---|
| cyc/px | 6.82/7.11 | 5.87/5.48 | **5.59/5.36** | 5.57/5.44 | 5.57/5.44 |
| flops | 6196 | 6247 | **6346** | 6541 | 6928 |

The knee is at **D=8**: 16 and 32 buy ≤0.3% for +195/+582 flops. Deeper is not
free and not faster.

---

## 6. Verification hooks

Which pattern proves which property — the mapping the planner should preserve
when it proposes a change:

| Property | Proven by |
|---|---|
| LUT mapping is correct for every input code | `lut_sweep`, `edge_cases` |
| Channels are not crossed | `channel_isolation` + distinct per-channel γ |
| Ordering preserved under backpressure | every pattern × `BP_PROFILE` |
| 1-cycle latency contract | `test_single_pixel_latency` |
| Full-rate throughput | `test_full_rate_throughput` + the `no_bp` guard |
| Reset clears control state | `test_reset_state` |
| Runtime LUT reload | `test_lut_reload` |
| Bit-exactness of all three models | SHA-256 frame hash per pattern |

Pattern order in `tb/test_set.py` is a contract — `build/sc_out.txt` is consumed
sequentially, so patterns may only be **appended**.

---

## 7. Δ-propagation

A precision or depth change is not a one-file edit. These must move together or
the scoreboard breaks:

| Change | `golden/gamma_golden.py` | `rtl/gamma.v` | `systemc/gamma_sc.h` |
|---|---|---|---|
| `PIXEL_W` | `PIXEL_W` | `PIXEL_W` | template arg |
| LUT size | `LUT_SIZE` | `LUT_DEPTH` | template arg |
| `FIFO_DEPTH` | — (untimed) | `FIFO_DEPTH` | `FIFO_DEPTH` |

`FIFO_DEPTH` has no golden counterpart: the golden model is untimed, so buffer
depth cannot change its output. That is the point — depth is provably a
timing-only knob.

---

## 8. Non-goals

Out of scope for this core, and therefore **not** covered by any current
evidence. Do not infer them:

- **Bus interface.** The LUT port is a raw write port. An APB/AHB/AXI-Lite shim
  is an integration concern.
- **AXI-Stream.** No `TUSER`/`TLAST`/`TKEEP`; the pixel interface is a bare
  ready/valid pair with no framing.
- **Clock domain crossing.** Single clock, no CDC.
- **Timing closure.** No STA, no target frequency, no process node. The
  `LUT_SYNC_READ=1` mode exists because a review flagged the combinational
  LUT→FIFO path as the likely Fmax limiter on FPGA, but that is a hypothesis,
  not a measurement.
- **X-propagation and reset-release behaviour.** See §4.3.

---

## 9. CHANGED

> Append proposed changes here before running `POST /plan`. The planner tags each
> step `NEW` / `MODIFIED` / `UNCHANGED` against the sections above, so an
> incremental regeneration touches only what actually moved. Leave this section
> empty when the design is at rest.

*(no pending changes)*
