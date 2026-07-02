"""Canonical validation test set: pattern list and per-channel LUTs.

Single definition shared by the cocotb testbench (tb/test_gamma.py) and the
SystemC input generator (scripts/gen_sc_inputs.py) so the two flows can never
drift apart. Pattern ORDER matters: sc_out.txt is consumed sequentially.

Per-channel gammas are deliberately distinct so that a swapped or crossed
channel in the DUT cannot produce a bit-exact match.
"""
from __future__ import annotations

import os

import numpy as np

import stimulus
from gamma_golden import build_lut

DEFAULT_GAMMAS = {"r": 2.2, "g": 1.8, "b": 2.8}


def luts_from_env() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-channel LUTs. GAMMA env var (single float) overrides all three
    channels — kept for the legacy single-gamma flow."""
    override = os.environ.get("GAMMA")
    if override is not None:
        g = float(override)
        gammas = {"r": g, "g": g, "b": g}
    else:
        gammas = DEFAULT_GAMMAS
    return (
        build_lut(gamma=gammas["r"]),
        build_lut(gamma=gammas["g"]),
        build_lut(gamma=gammas["b"]),
    )


def patterns() -> dict[str, np.ndarray]:
    """Ordered pattern registry. Append new patterns at the END to keep
    existing sc_out.txt offsets valid within a run."""
    return {
        "edge_cases":        stimulus.edge_cases(),
        "colorbar":          stimulus.colorbar(),
        "gradient":          stimulus.gradient(),
        "random_seed0":      stimulus.random_frame(seed=0),
        "lut_sweep":         stimulus.lut_sweep(),
        "channel_isolation": stimulus.channel_isolation(),
        "checkerboard":      stimulus.checkerboard(),
        "near_extremes":     stimulus.near_extremes(seed=1),
        # --- appended (order is the sc_out.txt contract; never reorder) ---
        "impulse":           stimulus.impulse(),
        "adjacent_codes":    stimulus.adjacent_codes(),
        "gamma_knee":        stimulus.gamma_knee(),
        "walking_ones":      stimulus.walking_ones(),
        "random_seed2":      stimulus.random_frame(seed=2),
    }


def total_pixels() -> int:
    return sum(p.reshape(-1, 3).shape[0] for p in patterns().values())
