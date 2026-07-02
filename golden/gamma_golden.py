"""Gamma correction golden model.

Single source of truth. SystemC and RTL outputs must match this bit-exactly.
"""
from __future__ import annotations

import hashlib
import numpy as np


LUT_SIZE = 256
PIXEL_W = 8


def build_lut(gamma: float = 2.2, out_w: int = PIXEL_W) -> np.ndarray:
    x = np.arange(LUT_SIZE, dtype=np.float64) / (LUT_SIZE - 1)
    y = np.power(x, 1.0 / gamma)
    q = np.round(y * ((1 << out_w) - 1)).astype(np.uint16)
    return q


def apply_gamma(pixels_rgb: np.ndarray, lut_r: np.ndarray, lut_g: np.ndarray, lut_b: np.ndarray) -> np.ndarray:
    assert pixels_rgb.dtype == np.uint8
    assert pixels_rgb.shape[-1] == 3
    out = np.empty_like(pixels_rgb, dtype=np.uint16)
    out[..., 0] = lut_r[pixels_rgb[..., 0]]
    out[..., 1] = lut_g[pixels_rgb[..., 1]]
    out[..., 2] = lut_b[pixels_rgb[..., 2]]
    return out


def frame_hash(pixels: np.ndarray) -> str:
    return hashlib.sha256(pixels.tobytes()).hexdigest()


if __name__ == "__main__":
    lut = build_lut()
    sample = np.array([[[0, 128, 255]]], dtype=np.uint8)
    out = apply_gamma(sample, lut, lut, lut)
    print("in", sample.tolist(), "->", out.tolist())
    print("hash", frame_hash(out))
