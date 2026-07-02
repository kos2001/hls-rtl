"""Integrity tests for the canonical test set (tb/test_set.py) and the
SystemC input generator (scripts/gen_sc_inputs.py).

The 3-way compare consumes sc_out.txt positionally, so the pattern registry,
the cocotb testbench, and the SystemC stimulus files must agree exactly.
"""
import numpy as np
import pytest

import gen_sc_inputs
import test_set
from gamma_golden import LUT_SIZE, build_lut

EXPECTED_ORDER = [
    "edge_cases", "colorbar", "gradient", "random_seed0",
    "lut_sweep", "channel_isolation", "checkerboard", "near_extremes",
    # appended patterns (append-only contract — sc_out.txt is positional)
    "impulse", "adjacent_codes", "gamma_knee", "walking_ones", "random_seed2",
]


class TestRegistry:
    def test_pattern_order_frozen(self):
        # sc_out.txt offsets depend on this order; changing it is a contract
        # change that must be deliberate.
        assert list(test_set.patterns().keys()) == EXPECTED_ORDER

    def test_total_pixels_consistent(self):
        total = sum(p.reshape(-1, 3).shape[0] for p in test_set.patterns().values())
        assert test_set.total_pixels() == total

    def test_patterns_deterministic(self):
        a = test_set.patterns()
        b = test_set.patterns()
        for name in a:
            assert np.array_equal(a[name], b[name]), f"{name} not reproducible"

    def test_full_lut_coverage_per_channel(self):
        # Across the whole set every LUT address of every channel is exercised.
        stacked = np.vstack([p.reshape(-1, 3) for p in test_set.patterns().values()])
        for ch in range(3):
            assert set(np.unique(stacked[:, ch])) == set(range(LUT_SIZE)), (
                f"channel {ch} leaves LUT entries unread"
            )


class TestLuts:
    def test_default_luts_are_per_channel_distinct(self, monkeypatch):
        monkeypatch.delenv("GAMMA", raising=False)
        lut_r, lut_g, lut_b = test_set.luts_from_env()
        assert not np.array_equal(lut_r, lut_g)
        assert not np.array_equal(lut_r, lut_b)
        assert not np.array_equal(lut_g, lut_b)

    def test_gamma_env_overrides_all_channels(self, monkeypatch):
        monkeypatch.setenv("GAMMA", "2.2")
        lut_r, lut_g, lut_b = test_set.luts_from_env()
        ref = build_lut(gamma=2.2)
        assert np.array_equal(lut_r, ref)
        assert np.array_equal(lut_g, ref)
        assert np.array_equal(lut_b, ref)


class TestGenScInputs:
    @pytest.fixture()
    def generated(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GAMMA", raising=False)
        gen_sc_inputs.main(tmp_path)
        return tmp_path

    def test_stim_matches_registry(self, generated):
        lines = (generated / "stim.txt").read_text().splitlines()
        stim = np.array([[int(v) for v in ln.split()] for ln in lines], dtype=np.uint16)
        expected = np.vstack([p.reshape(-1, 3) for p in test_set.patterns().values()])
        assert np.array_equal(stim, expected.astype(np.uint16))

    def test_lut_file_matches_luts_and_terminates(self, generated):
        lines = (generated / "lut.txt").read_text().splitlines()
        assert lines[-1] == "GO"
        entries = lines[:-1]
        assert len(entries) == 3 * LUT_SIZE
        luts = test_set.luts_from_env()
        for ln in entries:
            ch, addr, val = (int(v) for v in ln.split())
            assert val == int(luts[ch][addr])
