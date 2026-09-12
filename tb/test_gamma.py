"""3-way scoreboard: Python golden vs RTL DUT vs SystemC dump.

- Python golden: in-process via numpy.
- RTL DUT: cocotb drives signals, with randomized backpressure on both sides.
- SystemC: external simulator pre-run by `scripts/run_3way.sh`, output read from sc_out.txt.

Backpressure does not change pixel values — only ordering bubbles. Bit-exact
equality must still hold across all three models. Set BP_SEED / BP_IN_STALL /
BP_OUT_STALL env vars to control the stall profile.
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "golden"))
sys.path.insert(0, str(ROOT / "tb"))

from gamma_golden import build_lut, apply_gamma, frame_hash  # noqa: E402
import stimulus  # noqa: E402
import test_set  # noqa: E402


CLK_PERIOD_NS = 10
SC_OUT_PATH = ROOT / "build" / "sc_out.txt"


@dataclass
class BPProfile:
    """Backpressure profile. Stall probability is per-cycle; burst sets max stall length."""
    name: str
    in_stall_prob: float = 0.0
    in_stall_burst: int = 1
    out_stall_prob: float = 0.0
    out_stall_burst: int = 1


def profiles_from_env() -> list[BPProfile]:
    if os.environ.get("BP_PROFILE") == "single":
        return [BPProfile(
            "env",
            in_stall_prob=float(os.environ.get("BP_IN_STALL", "0.2")),
            in_stall_burst=int(os.environ.get("BP_IN_BURST", "3")),
            out_stall_prob=float(os.environ.get("BP_OUT_STALL", "0.2")),
            out_stall_burst=int(os.environ.get("BP_OUT_BURST", "3")),
        )]
    return [
        BPProfile("no_bp"),
        BPProfile("out_only", out_stall_prob=0.3, out_stall_burst=4),
        BPProfile("in_only",  in_stall_prob=0.3,  in_stall_burst=4),
        BPProfile("both_light", in_stall_prob=0.15, in_stall_burst=2,
                                out_stall_prob=0.15, out_stall_burst=2),
        BPProfile("both_heavy", in_stall_prob=0.5, in_stall_burst=6,
                                out_stall_prob=0.5, out_stall_burst=6),
    ]


async def reset(dut):
    dut.rst_n.value = 0
    dut.in_valid.value = 0
    dut.out_ready.value = 1
    dut.lut_we.value = 0
    dut.lut_ch.value = 0
    dut.lut_addr.value = 0
    dut.lut_wdata.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_lut(dut, lut_r, lut_g, lut_b):
    for ch, lut in enumerate([lut_r, lut_g, lut_b]):
        dut.lut_we.value = 1
        dut.lut_ch.value = ch
        for addr, val in enumerate(lut):
            dut.lut_addr.value = addr
            dut.lut_wdata.value = int(val)
            await RisingEdge(dut.clk)
    dut.lut_we.value = 0
    await RisingEdge(dut.clk)


async def run_pattern_with_bp(
    dut,
    pixels_flat: np.ndarray,
    bp: BPProfile,
    rng: random.Random,
    timeout_cycles: int,
) -> np.ndarray:
    """Drive pixels and collect outputs under a given backpressure profile."""
    target = len(pixels_flat)
    collected: list[tuple[int, int, int]] = []
    idx = 0
    in_stall_remaining = 0
    out_stall_remaining = 0

    async def sink():
        # ready driving + output collection in ONE coroutine: halves the
        # sink-side scheduler wakeups per cycle (measurable sim-time win).
        nonlocal out_stall_remaining
        while len(collected) < target:
            if out_stall_remaining > 0:
                dut.out_ready.value = 0
                out_stall_remaining -= 1
            else:
                dut.out_ready.value = 1
                if bp.out_stall_prob > 0 and rng.random() < bp.out_stall_prob:
                    out_stall_remaining = rng.randint(1, max(1, bp.out_stall_burst))
            await ReadOnly()
            if int(dut.out_valid.value) == 1 and int(dut.out_ready.value) == 1:
                collected.append((
                    int(dut.out_r.value),
                    int(dut.out_g.value),
                    int(dut.out_b.value),
                ))
            await RisingEdge(dut.clk)

    sink_task = cocotb.start_soon(sink())

    cycles = 0
    while idx < target:
        if in_stall_remaining > 0:
            dut.in_valid.value = 0
            in_stall_remaining -= 1
        else:
            if bp.in_stall_prob > 0 and rng.random() < bp.in_stall_prob:
                in_stall_remaining = rng.randint(1, max(1, bp.in_stall_burst))
                dut.in_valid.value = 0
            else:
                dut.in_valid.value = 1
                dut.in_r.value = int(pixels_flat[idx, 0])
                dut.in_g.value = int(pixels_flat[idx, 1])
                dut.in_b.value = int(pixels_flat[idx, 2])

        await ReadOnly()
        accepted = (
            int(dut.in_valid.value) == 1
            and int(dut.in_ready.value) == 1
            and in_stall_remaining == 0
        )
        await RisingEdge(dut.clk)
        if accepted:
            idx += 1

        cycles += 1
        assert cycles < timeout_cycles, f"timeout after {cycles} cycles in pattern (bp={bp.name})"

    dut.in_valid.value = 0

    drain_cycles = 0
    while len(collected) < target:
        await RisingEdge(dut.clk)
        drain_cycles += 1
        assert drain_cycles < timeout_cycles, f"drain timeout (bp={bp.name})"

    await sink_task

    dut.out_ready.value = 1
    total_cycles = cycles + drain_cycles
    return np.array(collected, dtype=np.uint16), total_cycles


def load_sc_dump(path: Path, n: int) -> np.ndarray | None:
    if not path.exists():
        return None
    out = []
    with path.open() as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 3:
                out.append([int(x) for x in parts])
            if len(out) >= n:
                break
    if not out:
        return None
    return np.array(out, dtype=np.uint16)


def diff_report(name: str, got: np.ndarray, ref: np.ndarray) -> str:
    if got.shape != ref.shape:
        return f"{name}: shape mismatch got={got.shape} ref={ref.shape}"
    mism = np.where(np.any(got != ref, axis=-1))[0]
    if mism.size == 0:
        return f"{name}: OK ({len(got)} pixels, hash={frame_hash(got)})"
    first = mism[0]
    return (
        f"{name}: MISMATCH at idx={first} "
        f"got={got[first].tolist()} ref={ref[first].tolist()} "
        f"({mism.size}/{len(got)} pixels differ)"
    )


async def run_pattern(dut, pattern_name, frame, lut_r, lut_g, lut_b, bp, rng, sc_out_full):
    flat = frame.reshape(-1, 3)
    golden = apply_gamma(frame, lut_r, lut_g, lut_b).reshape(-1, 3)
    timeout = max(1000, 50 * len(flat))
    rtl_out, cycles = await run_pattern_with_bp(dut, flat, bp, rng, timeout)

    tag = f"{pattern_name}/{bp.name}"
    cpp = cycles / len(flat)
    dut._log.info(f"[{tag}] golden hash={frame_hash(golden.astype(np.uint16))}")
    dut._log.info(f"[{tag}] throughput: {cycles} cycles / {len(flat)} px = {cpp:.3f} cyc/px")
    dut._log.info(f"[{tag}] {diff_report('RTL vs golden', rtl_out, golden)}")

    # Performance guard: with no backpressure the 1px/cycle pipeline must not
    # waste cycles. Allow a small fixed overhead for fill/drain + LUT-load tail.
    if bp.out_stall_prob == 0 and bp.in_stall_prob == 0:
        assert cycles <= len(flat) + 3, (
            f"{tag}: throughput regression — {cycles} cycles for {len(flat)} px "
            f"(expected <= {len(flat) + 3} at full rate)"
        )

    if sc_out_full is not None:
        sc_slice = sc_out_full[:len(flat)]
        dut._log.info(f"[{tag}] {diff_report('SC  vs golden', sc_slice, golden)}")
        dut._log.info(f"[{tag}] {diff_report('RTL vs SC    ', rtl_out, sc_slice)}")
        assert np.array_equal(sc_slice, golden), f"{tag}: SC vs golden mismatch"
    elif SC_OUT_PATH.exists():
        # Phase 2 passes no slice on purpose: the SystemC sim runs without
        # backpressure, so there is nothing to compare a stalled run against.
        # Saying "not found" here would be false, and this project treats a
        # skip as missing evidence — the two cases must not read alike.
        dut._log.info(f"[{tag}] SC compare not applicable (stall profile; the "
                      f"SystemC reference is generated at full rate)")
    else:
        dut._log.warning(f"[{tag}] SC dump not found at {SC_OUT_PATH}; skipping "
                         f"SC compare — build it with scripts/build_systemc.sh")

    assert np.array_equal(rtl_out, golden), f"{tag}: RTL vs golden mismatch"


@cocotb.test()
async def test_gamma_3way(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)

    seed = int(os.environ.get("BP_SEED", "0"))
    rng = random.Random(seed)
    dut._log.info(f"backpressure seed={seed}")

    lut_r, lut_g, lut_b = test_set.luts_from_env()
    await load_lut(dut, lut_r, lut_g, lut_b)

    patterns = test_set.patterns()
    total_pixels = test_set.total_pixels()
    sc_full = load_sc_dump(SC_OUT_PATH, total_pixels)

    mode = os.environ.get("BP_PROFILE", "split")

    if mode == "single":
        # Legacy/debug path: one env-defined profile across all patterns.
        bp = profiles_from_env()[0]
        dut._log.info(f"=== backpressure profile: {bp} ===")
        sc_cursor = 0
        for name, frame in patterns.items():
            n = frame.reshape(-1, 3).shape[0]
            sc_slice = sc_full[sc_cursor:sc_cursor + n] if sc_full is not None else None
            await run_pattern(dut, name, frame, lut_r, lut_g, lut_b, bp, rng, sc_slice)
            sc_cursor += n
        return

    if mode == "full":
        # Exhaustive cross-product (nightly): every pattern × every profile.
        for bp in profiles_from_env():
            dut._log.info(f"=== backpressure profile: {bp} ===")
            sc_cursor = 0
            for name, frame in patterns.items():
                n = frame.reshape(-1, 3).shape[0]
                sc_slice = sc_full[sc_cursor:sc_cursor + n] if sc_full is not None else None
                await run_pattern(dut, name, frame, lut_r, lut_g, lut_b, bp, rng, sc_slice)
                sc_cursor += n
        return

    # Default "split" mode: separate data coverage from protocol coverage.
    # Backpressure changes ordering, not values, so the full pattern×profile
    # cross-product is redundant. This preserves coverage at ~half the cycles.

    # Phase 1 — data coverage: every pattern at full rate (1 px/cycle).
    # SC compare lives here (the SystemC sim runs without backpressure).
    no_bp = BPProfile("no_bp")
    dut._log.info("=== phase 1: data coverage (no backpressure, all patterns) ===")
    sc_cursor = 0
    for name, frame in patterns.items():
        n = frame.reshape(-1, 3).shape[0]
        sc_slice = sc_full[sc_cursor:sc_cursor + n] if sc_full is not None else None
        await run_pattern(dut, name, frame, lut_r, lut_g, lut_b, no_bp, rng, sc_slice)
        sc_cursor += n

    # Phase 2 — protocol coverage: representative patterns under each stall
    # profile. gradient = all 256 codes; checkerboard = max line toggling.
    protocol_patterns = ["gradient", "checkerboard"]
    stall_profiles = [p for p in profiles_from_env() if p.name != "no_bp"]
    dut._log.info("=== phase 2: protocol coverage (stall profiles, "
                  f"patterns={protocol_patterns}) ===")
    for bp in stall_profiles:
        dut._log.info(f"--- backpressure profile: {bp.name} ---")
        for name in protocol_patterns:
            await run_pattern(dut, name, patterns[name], lut_r, lut_g, lut_b, bp, rng, None)


# ---------------------------------------------------------------------------
# Directed protocol tests (RTL only, no SystemC dependency)
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_reset_state(dut):
    """After reset: no stale output pending, DUT ready to accept."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)
    await ReadOnly()
    assert int(dut.out_valid.value) == 0, "out_valid must be deasserted after reset"
    assert int(dut.in_ready.value) == 1, "in_ready must be asserted after reset"


@cocotb.test()
async def test_single_pixel_latency(dut):
    """Exactly 1 cycle from accepted input to valid output, value bit-exact."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)
    lut_r, lut_g, lut_b = test_set.luts_from_env()
    await load_lut(dut, lut_r, lut_g, lut_b)

    pixel = (10, 20, 30)
    dut.out_ready.value = 1
    dut.in_valid.value = 1
    dut.in_r.value, dut.in_g.value, dut.in_b.value = pixel
    await ReadOnly()
    assert int(dut.in_ready.value) == 1, "DUT must accept with empty pipeline"
    await RisingEdge(dut.clk)
    dut.in_valid.value = 0
    await ReadOnly()
    assert int(dut.out_valid.value) == 1, "output must be valid 1 cycle after accept"
    got = (int(dut.out_r.value), int(dut.out_g.value), int(dut.out_b.value))
    exp = (int(lut_r[pixel[0]]), int(lut_g[pixel[1]]), int(lut_b[pixel[2]]))
    assert got == exp, f"single-pixel mismatch got={got} exp={exp}"
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.out_valid.value) == 0, "out_valid must drop once consumed"


@cocotb.test()
async def test_full_rate_throughput(dut):
    """With no stalls the DUT must sustain 1 pixel/cycle: in_ready never
    drops and every cycle after the first carries a valid output."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)
    lut_r, lut_g, lut_b = test_set.luts_from_env()
    await load_lut(dut, lut_r, lut_g, lut_b)

    n = 64
    pixels = stimulus.random_frame(width=n, height=1, seed=2).reshape(-1, 3)
    golden = apply_gamma(pixels.reshape(1, n, 3), lut_r, lut_g, lut_b).reshape(-1, 3)

    dut.out_ready.value = 1
    collected = []
    for i in range(n):
        dut.in_valid.value = 1
        dut.in_r.value = int(pixels[i, 0])
        dut.in_g.value = int(pixels[i, 1])
        dut.in_b.value = int(pixels[i, 2])
        await ReadOnly()
        assert int(dut.in_ready.value) == 1, f"in_ready dropped at pixel {i} with no backpressure"
        if i > 0:
            assert int(dut.out_valid.value) == 1, f"output bubble at pixel {i} with no stalls"
        if int(dut.out_valid.value) == 1:
            collected.append((int(dut.out_r.value), int(dut.out_g.value), int(dut.out_b.value)))
        await RisingEdge(dut.clk)
    dut.in_valid.value = 0
    await ReadOnly()
    assert int(dut.out_valid.value) == 1, "last output missing"
    collected.append((int(dut.out_r.value), int(dut.out_g.value), int(dut.out_b.value)))
    await RisingEdge(dut.clk)

    got = np.array(collected, dtype=np.uint16)
    assert len(got) == n, f"throughput loss: {len(got)}/{n} outputs in {n + 1} cycles"
    assert np.array_equal(got, golden), "full-rate stream data mismatch"


@cocotb.test()
async def test_lut_reload(dut):
    """LUTs are reloadable at runtime: identity pass-through first, then a
    gamma curve, both bit-exact against the golden model."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)
    rng = random.Random(3)
    bp = BPProfile("no_bp")
    frame = stimulus.gradient()
    flat = frame.reshape(-1, 3)
    timeout = max(1000, 50 * len(flat))

    identity = np.arange(256, dtype=np.uint16)
    await load_lut(dut, identity, identity, identity)
    out, _ = await run_pattern_with_bp(dut, flat, bp, rng, timeout)
    assert np.array_equal(out, flat.astype(np.uint16)), "identity LUT must pass pixels through"

    lut_r, lut_g, lut_b = test_set.luts_from_env()
    await load_lut(dut, lut_r, lut_g, lut_b)
    golden = apply_gamma(frame, lut_r, lut_g, lut_b).reshape(-1, 3)
    out, _ = await run_pattern_with_bp(dut, flat, bp, rng, timeout)
    assert np.array_equal(out, golden), "reloaded gamma LUT output mismatch"


@cocotb.test()
async def test_lut_reserved_encoding(dut):
    """`lut_ch = 2'b11` is reserved and must not write any channel.

    The RTL states this as a contract ("reserved encoding -> no write") and
    nothing exercised it: the `default:` arm was the one line in the module that
    line coverage reported as never reached. An unreached contract is a contract
    nobody checks — a decoder that quietly aliased the reserved code onto a real
    channel would corrupt a LUT and pass every other test here.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset(dut)

    identity = np.arange(256, dtype=np.uint16)
    await load_lut(dut, identity, identity, identity)

    # Write a value that is wrong for every channel, using the reserved code.
    POISON = 0x5A
    dut.lut_we.value = 1
    dut.lut_ch.value = 3            # reserved
    for addr in (0, 1, 128, 255):
        dut.lut_addr.value = addr
        dut.lut_wdata.value = POISON
        await RisingEdge(dut.clk)
    dut.lut_we.value = 0
    await RisingEdge(dut.clk)

    # Every LUT must be untouched, so the identity mapping still holds.
    probe = np.array([[0, 0, 0], [1, 1, 1], [128, 128, 128], [255, 255, 255]],
                     dtype=np.uint8)
    rng = random.Random(11)
    out, _ = await run_pattern_with_bp(dut, probe, BPProfile("no_bp"), rng, 1000)
    assert np.array_equal(out, probe.astype(np.uint16)), (
        f"reserved lut_ch=2'b11 wrote into a LUT: got {out.tolist()}, "
        f"expected the identity mapping {probe.tolist()}")
