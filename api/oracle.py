"""Golden-as-oracle (improvement #2).

Spec2RTL-Agent generates code but has no executable ground truth, so it leans on
human review to catch functional (not just syntactic) errors. Here the Python
golden IS the oracle: from a reference function + the stimulus set we
auto-derive the verification contract (expected output + SHA-256 per pattern)
that any candidate representation (SystemC, RTL, or LLM-generated code) must
satisfy bit-exactly — no hand-written testbench, no human in the value-check
loop.

This wraps the gamma golden today, but the Oracle is reference-agnostic: point
it at any `apply_fn(frame, *luts)` + pattern dict and it yields the same
contract + check primitive.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
for _p in ("golden", "tb"):
    _sp = str(_ROOT / _p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from gamma_golden import apply_gamma, frame_hash  # noqa: E402
import test_set  # noqa: E402


class Oracle:
    """Reference-model oracle: derives expected outputs + hashes and checks
    candidate outputs against them."""

    def __init__(self, apply_fn: Callable[..., np.ndarray],
                 patterns: Dict[str, np.ndarray], luts: tuple):
        self.apply_fn = apply_fn
        self.patterns = patterns
        self.luts = luts

    def expected(self, name: str) -> np.ndarray:
        frame = self.patterns[name]
        return self.apply_fn(frame, *self.luts).reshape(-1, 3).astype(np.uint16)

    def contract(self) -> dict:
        rows = []
        for name in self.patterns:
            exp = self.expected(name)
            rows.append({"name": name, "pixels": int(exp.shape[0]),
                         "sha256": frame_hash(exp)})
        return {
            "reference": "gamma_golden.apply_gamma",
            "patterns": rows,
            "total_pixels": sum(r["pixels"] for r in rows),
            "note": "Auto-derived scoreboard contract; any SystemC/RTL/LLM "
                    "candidate must reproduce these hashes bit-exactly.",
        }

    def check(self, name: str, candidate: List[List[int]]) -> dict:
        if name not in self.patterns:
            return {"ok": False, "error": f"unknown pattern '{name}'"}
        exp = self.expected(name)
        cand = np.asarray(candidate, dtype=np.uint16)
        if cand.shape != exp.shape:
            return {"ok": False, "error": f"shape {cand.shape} != expected {exp.shape}"}
        mism = np.where(np.any(cand != exp, axis=-1))[0]
        if mism.size == 0:
            return {"ok": True, "pixels": int(exp.shape[0]), "sha256": frame_hash(exp)}
        i = int(mism[0])
        return {"ok": False, "mismatch_index": i, "mismatches": int(mism.size),
                "expected": exp[i].tolist(), "got": cand[i].tolist()}


def gamma_oracle() -> Oracle:
    return Oracle(apply_gamma, test_set.patterns(), test_set.luts_from_env())
