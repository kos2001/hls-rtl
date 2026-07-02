"""Generate stim.txt + lut.txt for the standalone SystemC simulator.

Must produce the same stimulus order as tb/test_gamma.py so that sc_out.txt
can be replayed against the cocotb collector.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "golden"))
sys.path.insert(0, str(ROOT / "tb"))

import test_set  # noqa: E402


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lut_r, lut_g, lut_b = test_set.luts_from_env()

    with (out_dir / "lut.txt").open("w") as f:
        for ch, lut in enumerate([lut_r, lut_g, lut_b]):
            for addr, val in enumerate(lut):
                f.write(f"{ch} {addr} {int(val)}\n")
        f.write("GO\n")

    with (out_dir / "stim.txt").open("w") as f:
        for frame in test_set.patterns().values():
            for px in frame.reshape(-1, 3):
                f.write(f"{int(px[0])} {int(px[1])} {int(px[2])}\n")


if __name__ == "__main__":
    main(ROOT / "build")
