"""Unit tests for the stimulus generators (tb/stimulus.py).

Every pattern feeding the 3-way scoreboard must be deterministic, uint8 RGB,
and actually deliver the coverage it claims.
"""
import numpy as np
import pytest

import stimulus

ALL_PATTERNS = {
    "colorbar": stimulus.colorbar,
    "gradient": stimulus.gradient,
    "random_frame": stimulus.random_frame,
    "edge_cases": stimulus.edge_cases,
    "lut_sweep": stimulus.lut_sweep,
    "channel_isolation": stimulus.channel_isolation,
    "checkerboard": stimulus.checkerboard,
    "near_extremes": stimulus.near_extremes,
    "impulse": stimulus.impulse,
    "adjacent_codes": stimulus.adjacent_codes,
    "gamma_knee": stimulus.gamma_knee,
    "walking_ones": stimulus.walking_ones,
}


@pytest.mark.parametrize("name,gen", ALL_PATTERNS.items(), ids=ALL_PATTERNS.keys())
class TestCommonContract:
    def test_dtype_uint8(self, name, gen):
        assert gen().dtype == np.uint8

    def test_rgb_last_axis(self, name, gen):
        frame = gen()
        assert frame.ndim == 3
        assert frame.shape[-1] == 3

    def test_deterministic(self, name, gen):
        assert np.array_equal(gen(), gen())


class TestGradient:
    def test_covers_all_codes(self):
        frame = stimulus.gradient()
        for ch in range(3):
            assert set(np.unique(frame[..., ch])) == set(range(256))


class TestRandomFrame:
    def test_seed_changes_content(self):
        assert not np.array_equal(stimulus.random_frame(seed=0), stimulus.random_frame(seed=1))

    def test_shape(self):
        assert stimulus.random_frame(width=10, height=4).shape == (4, 10, 3)


class TestEdgeCases:
    def test_contains_extremes(self):
        frame = stimulus.edge_cases()
        assert 0 in frame and 255 in frame


class TestLutSweep:
    def test_every_lut_entry_read_once_per_channel(self):
        flat = stimulus.lut_sweep().reshape(-1, 3)
        assert len(flat) == 256
        for ch in range(3):
            counts = np.bincount(flat[:, ch], minlength=256)
            assert np.all(counts == 1), f"channel {ch} does not cover each code exactly once"

    def test_channels_decorrelated(self):
        # If channels were equal, a swapped channel would still pass.
        flat = stimulus.lut_sweep().reshape(-1, 3)
        assert not np.array_equal(flat[:, 0], flat[:, 1])
        assert not np.array_equal(flat[:, 0], flat[:, 2])
        assert not np.array_equal(flat[:, 1], flat[:, 2])


class TestChannelIsolation:
    def test_one_active_channel_per_row(self):
        frame = stimulus.channel_isolation()
        assert frame.shape == (3, 256, 3)
        ramp = np.arange(256, dtype=np.uint8)
        for row, active in enumerate(range(3)):
            for ch in range(3):
                if ch == active:
                    assert np.array_equal(frame[row, :, ch], ramp)
                else:
                    assert np.all(frame[row, :, ch] == 0)


class TestCheckerboard:
    def test_only_extremes(self):
        frame = stimulus.checkerboard()
        assert set(np.unique(frame)) == {0, 255}

    def test_alternates_every_pixel(self):
        frame = stimulus.checkerboard()
        assert np.all(frame[:, :-1] != frame[:, 1:]), "horizontal neighbors must differ"
        assert np.all(frame[:-1, :] != frame[1:, :]), "vertical neighbors must differ"


class TestNearExtremes:
    def test_only_boundary_values(self):
        pool = {0, 1, 2, 127, 128, 129, 253, 254, 255}
        frame = stimulus.near_extremes()
        assert set(np.unique(frame)).issubset(pool)

    def test_seed_changes_content(self):
        assert not np.array_equal(stimulus.near_extremes(seed=1), stimulus.near_extremes(seed=2))


class TestImpulse:
    def test_single_nonzero_pixel(self):
        frame = stimulus.impulse()
        assert int(np.count_nonzero(frame.any(axis=-1))) == 1
        assert frame.max() == 255

    def test_is_max_pixel(self):
        frame = stimulus.impulse()
        ys, xs = np.where(frame.any(axis=-1))
        assert np.array_equal(frame[ys[0], xs[0]], [255, 255, 255])


class TestAdjacentCodes:
    def test_consecutive_per_channel(self):
        flat = stimulus.adjacent_codes().reshape(-1, 3)
        assert len(flat) == 256
        # Each channel is the previous channel shifted by one code (mod 256).
        assert np.array_equal(flat[:, 1], (flat[:, 0].astype(int) + 1) % 256)
        assert np.array_equal(flat[:, 2], (flat[:, 0].astype(int) + 2) % 256)

    def test_channels_decorrelated(self):
        flat = stimulus.adjacent_codes().reshape(-1, 3)
        assert not np.array_equal(flat[:, 0], flat[:, 1])


class TestGammaKnee:
    def test_in_steep_low_region(self):
        assert stimulus.gamma_knee().max() < 16

    def test_seed_deterministic(self):
        assert np.array_equal(stimulus.gamma_knee(seed=7), stimulus.gamma_knee(seed=7))


class TestWalkingOnes:
    def test_address_bit_lanes(self):
        flat = stimulus.walking_ones().reshape(-1, 3)
        expected = {0, 255} | {1 << b for b in range(8)}
        assert set(np.unique(flat[:, 0])) == expected

    def test_channels_rotated(self):
        flat = stimulus.walking_ones().reshape(-1, 3)
        assert not np.array_equal(flat[:, 0], flat[:, 1])
        assert not np.array_equal(flat[:, 1], flat[:, 2])
