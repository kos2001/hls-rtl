"""Progressive-coding oracle (improvement #1).

Spec2RTL-Agent argues for NL -> synthesizable C++ -> HLS -> RTL instead of
NL -> RTL directly, because the intermediate representation is easier to get
correct. The weakness of that flow is that it has no ground-truth reference.

This project does: the Python golden model is the executable reference, and the
3-way scoreboard proves each *representation* (SystemC, RTL) bit-exact against
it. This module surfaces that as the oracle for a progressive-coding flow — a
representation x pattern equivalence matrix, computed by actually running the
cocotb regression rather than assuming RTL == golden.

  golden (Python)  — reference rung (defines the expected hashes)
  systemc (C++)    — HLS-side representation (compared if build/sc_out.txt exists)
  rtl (Verilog)    — synthesizable representation (always compared)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

_ROOT = Path(__file__).resolve().parents[1]
_TB_DIR = _ROOT / "tb"
# Import-order independent: ensure the golden model / generator are importable
# regardless of who imports this module first.
for _p in ("scripts", "golden", "tb"):
    _sp = str(_ROOT / _p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from gen_dashboard_data import build_results  # noqa: E402

from .config import sim_env  # noqa: E402

# e.g. "[gradient/no_bp] RTL vs golden: OK (2048 pixels, hash=99fc...)"
_CMP_RE = re.compile(
    r"\[(?P<pat>\w+)/(?P<prof>\w+)\]\s+(?P<who>RTL vs golden|SC\s+vs golden)\s*:\s*(?P<verdict>OK|MISMATCH)"
)




def _run_regression(timeout: int) -> str:
    try:
        proc = subprocess.run(["make", "-s"], cwd=str(_TB_DIR), capture_output=True,
                              text=True, timeout=timeout, env=sim_env())
        return proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def run_progressive(*, run_regression: bool = True, timeout: int = 300) -> dict:
    golden = build_results()
    pattern_names = [p["name"] for p in golden["patterns"]]
    golden_hash = {p["name"]: p["golden_sha256"] for p in golden["patterns"]}

    rtl_status: Dict[str, str] = {n: "unknown" for n in pattern_names}
    sc_status: Dict[str, str] = {n: "skip" for n in pattern_names}

    log = _run_regression(timeout) if run_regression else ""
    for m in _CMP_RE.finditer(log):
        pat, who, verdict = m["pat"], m["who"], m["verdict"]
        if pat not in rtl_status:
            continue
        ok = verdict == "OK"
        if who.startswith("RTL"):
            # any MISMATCH for this pattern marks it failed
            if rtl_status[pat] != "fail":
                rtl_status[pat] = "pass" if ok else "fail"
            if not ok:
                rtl_status[pat] = "fail"
        else:  # SC vs golden
            if sc_status[pat] != "fail":
                sc_status[pat] = "pass" if ok else "fail"
            if not ok:
                sc_status[pat] = "fail"

    def rung(name: str, role: str, status_map: Dict[str, str]) -> dict:
        pats = [{"name": n, "status": status_map[n], "golden_sha256": golden_hash[n]}
                for n in pattern_names]
        statuses = {p["status"] for p in pats}
        overall = ("fail" if "fail" in statuses
                   else "skip" if statuses == {"skip"}
                   else "pass" if statuses <= {"pass"} else "partial")
        return {"name": name, "role": role, "overall": overall, "patterns": pats}

    representations = [
        rung("golden", "reference", {n: "pass" for n in pattern_names}),
        rung("systemc", "hls-intermediate", sc_status),
        rung("rtl", "synthesizable", rtl_status),
    ]
    bit_exact = all(r["overall"] in ("pass", "skip") for r in representations)
    return {
        "design": golden["design"],
        "patterns_total": len(pattern_names),
        "representations": representations,
        "bit_exact": bit_exact,
        "note": "Golden Python is the oracle; each representation is proven "
                "bit-exact against it by the 3-way scoreboard (SystemC compared "
                "only when build/sc_out.txt is present).",
    }
