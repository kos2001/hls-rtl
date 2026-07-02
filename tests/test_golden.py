"""Unit tests for the golden model (golden/gamma_golden.py).

The golden model is the single source of truth for the 3-way scoreboard, so
its own properties must be locked down independently of any simulator.
"""
import numpy as np
import pytest

from gamma_golden import LUT_SIZE, PIXEL_W, apply_gamma, build_lut, frame_hash


class TestBuildLut:
    def test_shape_and_dtype(self):
        lut = build_lut()
        assert lut.shape == (LUT_SIZE,)
        assert lut.dtype == np.uint16

    def test_endpoints_pinned(self):
        # Gamma curves must map black to black and white to white.
        for gamma in (1.0, 1.8, 2.2, 2.8):
            lut = build_lut(gamma=gamma)
            assert lut[0] == 0, f"gamma={gamma}: lut[0] != 0"
            assert lut[-1] == (1 << PIXEL_W) - 1, f"gamma={gamma}: lut[255] != 255"

    def test_values_fit_output_width(self):
        for gamma in (0.5, 1.0, 2.2, 2.8):
            lut = build_lut(gamma=gamma)
            assert lut.max() <= (1 << PIXEL_W) - 1

    def test_monotonic_nondecreasing(self):
        # x^(1/gamma) is monotonic; quantization must not break ordering.
        for gamma in (0.5, 1.0, 1.8, 2.2, 2.8):
            lut = build_lut(gamma=gamma)
            assert np.all(np.diff(lut.astype(np.int32)) >= 0), f"gamma={gamma} not monotonic"

    def test_gamma_one_is_identity(self):
        lut = build_lut(gamma=1.0)
        assert np.array_equal(lut, np.arange(LUT_SIZE))

    def test_decoding_gamma_brightens_midtones(self):
        # 1/gamma encode with gamma > 1 lifts every interior code point.
        lut = build_lut(gamma=2.2)
        interior = np.arange(1, LUT_SIZE - 1)
        assert np.all(lut[interior] >= interior)
        assert lut[128] > 128

    def test_known_reference_values(self):
        # Frozen anchors: round(255 * (x/255)^(1/2.2)).
        lut = build_lut(gamma=2.2)
        assert lut[1] == round(255 * (1 / 255) ** (1 / 2.2))
        assert lut[128] == round(255 * (128 / 255) ** (1 / 2.2))
        assert lut[254] == round(255 * (254 / 255) ** (1 / 2.2))

    def test_distinct_gammas_distinct_luts(self):
        # Per-channel swap detection relies on this.
        assert not np.array_equal(build_lut(gamma=2.2), build_lut(gamma=1.8))
        assert not np.array_equal(build_lut(gamma=2.2), build_lut(gamma=2.8))


class TestApplyGamma:
    def test_matches_naive_lookup(self):
        rng = np.random.default_rng(0)
        frame = rng.integers(0, 256, size=(4, 7, 3), dtype=np.uint8)
        lut_r, lut_g, lut_b = build_lut(2.2), build_lut(1.8), build_lut(2.8)
        out = apply_gamma(frame, lut_r, lut_g, lut_b)
        for y in range(frame.shape[0]):
            for x in range(frame.shape[1]):
                r, g, b = frame[y, x]
                assert out[y, x, 0] == lut_r[r]
                assert out[y, x, 1] == lut_g[g]
                assert out[y, x, 2] == lut_b[b]

    def test_channel_routing(self):
        # Distinct constant LUTs per channel: any swap is visible.
        frame = np.full((2, 2, 3), 7, dtype=np.uint8)
        lut_r = np.full(LUT_SIZE, 11, dtype=np.uint16)
        lut_g = np.full(LUT_SIZE, 22, dtype=np.uint16)
        lut_b = np.full(LUT_SIZE, 33, dtype=np.uint16)
        out = apply_gamma(frame, lut_r, lut_g, lut_b)
        assert np.all(out[..., 0] == 11)
        assert np.all(out[..., 1] == 22)
        assert np.all(out[..., 2] == 33)

    def test_shape_preserved(self):
        frame = np.zeros((3, 5, 3), dtype=np.uint8)
        lut = build_lut()
        assert apply_gamma(frame, lut, lut, lut).shape == frame.shape

    def test_rejects_non_uint8(self):
        lut = build_lut()
        frame = np.zeros((1, 1, 3), dtype=np.uint16)
        with pytest.raises(AssertionError):
            apply_gamma(frame, lut, lut, lut)


class TestFrameHash:
    def test_deterministic(self):
        frame = np.arange(48, dtype=np.uint16).reshape(4, 4, 3)
        assert frame_hash(frame) == frame_hash(frame.copy())

    def test_sensitive_to_single_pixel(self):
        frame = np.zeros((4, 4, 3), dtype=np.uint16)
        tweaked = frame.copy()
        tweaked[2, 1, 0] = 1
        assert frame_hash(frame) != frame_hash(tweaked)

    def test_sensitive_to_dtype(self):
        # The scoreboard hashes uint16 buffers; a dtype change must not alias.
        a = np.zeros((2, 2, 3), dtype=np.uint8)
        b = np.zeros((2, 2, 3), dtype=np.uint16)
        assert frame_hash(a) != frame_hash(b)
