"""Pixel stimulus generators."""
from __future__ import annotations

import numpy as np


def colorbar(width: int = 64, height: int = 8) -> np.ndarray:
    bars = np.array([
        [255, 255, 255], [255, 255, 0], [0, 255, 255], [0, 255, 0],
        [255, 0, 255], [255, 0, 0], [0, 0, 255], [0, 0, 0],
    ], dtype=np.uint8)
    cols = np.repeat(bars, width // len(bars), axis=0)
    if cols.shape[0] < width:
        pad = np.tile(cols[-1:], (width - cols.shape[0], 1))
        cols = np.vstack([cols, pad])
    return np.tile(cols, (height, 1, 1))


def gradient(width: int = 256, height: int = 8) -> np.ndarray:
    row = np.stack([np.arange(width, dtype=np.uint8)] * 3, axis=-1)
    return np.tile(row, (height, 1, 1))


def random_frame(width: int = 64, height: int = 8, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def edge_cases() -> np.ndarray:
    rows = [
        [[0, 0, 0]] * 8,
        [[255, 255, 255]] * 8,
        [[0, 128, 255], [255, 128, 0], [128, 0, 255], [128, 255, 0]] * 2,
    ]
    return np.array(rows, dtype=np.uint8)


def lut_sweep() -> np.ndarray:
    """Every LUT entry of every channel is read exactly once, decorrelated
    across channels so a swapped/crossed channel cannot alias to a pass."""
    i = np.arange(256, dtype=np.uint16)
    frame = np.stack([i % 256, (i + 85) % 256, (i + 170) % 256], axis=-1)
    return frame.reshape(1, 256, 3).astype(np.uint8)


def channel_isolation() -> np.ndarray:
    """One channel ramps 0..255 while the other two stay 0.
    Catches channel swap and crosstalk between LUTs."""
    ramp = np.arange(256, dtype=np.uint8)
    zeros = np.zeros(256, dtype=np.uint8)
    rows = [
        np.stack([ramp, zeros, zeros], axis=-1),
        np.stack([zeros, ramp, zeros], axis=-1),
        np.stack([zeros, zeros, ramp], axis=-1),
    ]
    return np.stack(rows, axis=0)


def checkerboard(width: int = 64, height: int = 8) -> np.ndarray:
    """Alternating min/max pixels: max simultaneous toggling on the datapath."""
    idx = np.add.outer(np.arange(height), np.arange(width)) % 2
    frame = np.repeat(np.where(idx == 0, 0, 255)[..., None], 3, axis=-1)
    return frame.astype(np.uint8)


def near_extremes(width: int = 64, height: int = 8, seed: int = 1) -> np.ndarray:
    """Random pixels biased to LUT-index boundaries (0/255) and the midpoint,
    where quantization steps in the gamma curve are most likely to disagree."""
    pool = np.array([0, 1, 2, 127, 128, 129, 253, 254, 255], dtype=np.uint8)
    rng = np.random.default_rng(seed)
    return pool[rng.integers(0, len(pool), size=(height, width, 3))]


def impulse(width: int = 32, height: int = 4) -> np.ndarray:
    """A single max pixel in a field of zeros. Catches stuck enables and an
    output register that fails to update for a lone valid pixel surrounded by
    minimum-value neighbors."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[height // 2, width // 2] = 255
    return frame


def adjacent_codes() -> np.ndarray:
    """Consecutive code pairs (c, c+1) per channel, channels offset by one so an
    off-by-one address error on any single channel changes the output (a plain
    ramp with correlated channels would not localize the faulting lane)."""
    c = np.arange(256, dtype=np.uint16)
    frame = np.stack([c, (c + 1) % 256, (c + 2) % 256], axis=-1)
    return frame.reshape(1, 256, 3).astype(np.uint8)


def gamma_knee(width: int = 64, height: int = 4, seed: int = 7) -> np.ndarray:
    """Codes clustered in the steep low region of the gamma curve (0..15),
    where adjacent inputs map to maximally different outputs — the most
    sensitive place for LUT-content / rounding errors. Channels drawn
    independently, so they are decorrelated."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 16, size=(height, width, 3), dtype=np.uint8)


def walking_ones() -> np.ndarray:
    """Per-channel walking-one address codes (0, 1, 2, 4, ... 128, 255):
    exercises each input bit lane independently — catches a stuck or swapped
    address bit. Channels are rotated so a channel swap is observable."""
    codes = np.array([0] + [1 << b for b in range(8)] + [255], dtype=np.uint8)
    frame = np.stack([codes, np.roll(codes, 1), np.roll(codes, 2)], axis=-1)
    return frame.reshape(1, codes.size, 3)
