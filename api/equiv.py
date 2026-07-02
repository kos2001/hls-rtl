"""Logical equivalence checking (improvement #7, yosys LEC).

For incremental regeneration to be safe we must prove the new RTL is logically
equivalent to the old one (outside the intentionally-changed modules). This runs
yosys sequential equivalence (equiv_make + equiv_induct).

LEC over the full 8-bit design instantiates 3x256-entry memories, which is heavy
for induction; by default we shrink the parameters (PIXEL_W=2, LUT_DEPTH=4) for
a tractable structural proof. Self-equivalence is exact at any size; a real
logic divergence (e.g. a swapped channel) is caught at the reduced size too.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_TIMEOUT = 120


@dataclass
class EquivResult:
    equivalent: bool
    available: bool
    status: str
    issues: List[str]
    log_tail: str = ""

    def to_dict(self) -> dict:
        return {"equivalent": self.equivalent, "available": self.available,
                "status": self.status, "issues": self.issues, "log_tail": self.log_tail}


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def check_equivalence(old_code: str, new_code: str, *, top: str = "gamma",
                      pixel_w: int = 2, lut_depth: int = 4) -> EquivResult:
    if not yosys_available():
        return EquivResult(False, False, "unavailable", ["yosys not installed"])
    def _renamed(code: str, name: str) -> str:
        # Give each design a distinct module name so both can be read at once
        # (a `hierarchy -top` per design would prune the other).
        body = re.sub(rf"\bmodule\s+{re.escape(top)}\b", f"module {name}", code, count=1)
        return body if body.endswith("\n") else body + "\n"

    with tempfile.TemporaryDirectory() as td:
        gold = Path(td) / "gold.v"
        gate = Path(td) / "gate.v"
        gold.write_text(_renamed(old_code, "gold"))
        gate.write_text(_renamed(new_code, "gate"))
        script = "; ".join([
            f"read_verilog {gold} {gate}",
            f"chparam -set PIXEL_W {pixel_w} -set LUT_DEPTH {lut_depth} gold",
            f"chparam -set PIXEL_W {pixel_w} -set LUT_DEPTH {lut_depth} gate",
            "proc", "opt", "memory", "opt",
            "equiv_make gold gate equiv",
            "hierarchy -top equiv",
            "clk2fflogic", "equiv_simple", "equiv_induct",
            "equiv_status -assert",
        ])
        proc = subprocess.run(["yosys", "-p", script], capture_output=True,
                              text=True, timeout=_TIMEOUT)
    out = proc.stdout + proc.stderr
    tail = "\n".join(out.splitlines()[-12:])
    # equiv_status reports "Equivalence successfully proven!" and -assert exits 0.
    proven = proc.returncode == 0 and "successfully proven" in out.lower()
    if proven:
        return EquivResult(True, True, "equivalent", [], tail)
    unproven = re.search(r"(\d+)\s+unproven", out.lower())
    status = "not_equivalent" if (unproven or proc.returncode != 0) else "inconclusive"
    issues = [l for l in out.splitlines() if "ERROR" in l.upper() or "unproven" in l.lower()][:4]
    return EquivResult(False, True, status, issues, tail)
