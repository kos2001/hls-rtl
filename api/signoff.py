"""RTL sign-off ladder for the gamma project.

Runs the full quality ladder on the project RTL and produces a consolidated
verdict:

  1. lint       — verilator static elaboration            (gating)
  2. design     — structural design-rule checks            (gating; errors gate)
  3. synthesize — yosys generic synthesis must succeed      (gating)
  4. simulate   — the real 3-way cocotb regression passes   (gating)

SIGNED_OFF requires every applicable gating stage to pass. A stage whose tool
is unavailable is reported `skip` and downgrades the verdict to CONDITIONAL.

Ported/adapted from ai_driven_rtl/src/signoff.py; the simulate stage runs this
project's actual cocotb 3-way scoreboard (tb/Makefile) rather than a generated
testbench.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import rtl_qor
from .config import sim_env
from .telemetry import archive

_ROOT = Path(__file__).resolve().parents[1]
_TB_DIR = _ROOT / "tb"


@dataclass
class Stage:
    name: str
    status: str  # "pass" | "fail" | "skip"
    gating: bool
    detail: str = ""


def _verdict(stages: List[Stage]) -> str:
    gating = [s for s in stages if s.gating]
    if any(s.status == "fail" for s in gating):
        return "REJECTED"
    if any(s.status == "skip" for s in gating):
        return "CONDITIONAL"
    return "SIGNED_OFF"




def _run_regression(timeout: int) -> Stage:
    """Run the cocotb 3-way scoreboard via tb/Makefile and parse the result."""
    if not rtl_qor.verilator_available():
        return Stage("simulate", "skip", True, "verilator not available")
    try:
        proc = subprocess.run(
            ["make", "-s"], cwd=str(_TB_DIR), capture_output=True, text=True,
            timeout=timeout, env=sim_env(),
        )
    except subprocess.TimeoutExpired:
        return Stage("simulate", "fail", True, f"regression timed out after {timeout}s")
    out = proc.stdout + proc.stderr
    m = re.search(r"TESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)", out)
    if not m:
        return Stage("simulate", "fail", True, "could not parse cocotb results")
    total, passed, failed = (int(m.group(i)) for i in (1, 2, 3))
    ok = failed == 0 and proc.returncode == 0
    return Stage("simulate", "pass" if ok else "fail", True,
                 f"{passed}/{total} cocotb tests pass")


def run_signoff(*, run_regression: bool = True, sim_timeout: int = 300) -> dict:
    report = rtl_qor.analyze()
    stages: List[Stage] = []

    lint_pass = report.metrics.get("lint_pass")
    if lint_pass is None:
        stages.append(Stage("lint", "skip", True, "verilator not available"))
    else:
        stages.append(Stage("lint", "pass" if lint_pass else "fail", True,
                            f"{report.lint_tool}: {report.metrics.get('lint_finding_count', 0)} findings"))

    failing_errors = [c for c in report.checks
                      if c.severity == "error" and not c.ok
                      and c.id not in ("synthesizable", "lint_clean")]
    stages.append(Stage("design", "pass" if not failing_errors else "fail", True,
                        "; ".join(c.detail for c in failing_errors) or "structural checks ok"))

    synth = report.metrics.get("synthesizable")
    if synth is None:
        stages.append(Stage("synthesize", "skip", True, "yosys not available"))
    else:
        stages.append(Stage("synthesize", "pass" if synth else "fail", True,
                            f"cells={report.metrics.get('synth_cells')} "
                            f"flops={report.metrics.get('synth_flops')}"))

    if run_regression:
        stages.append(_run_regression(sim_timeout))
    else:
        stages.append(Stage("simulate", "skip", True, "regression not requested"))

    verdict = _verdict(stages)
    result = {
        "verdict": verdict,
        "score": report.score,
        "grade": report.grade,
        "module": report.module,
        "stages": [s.__dict__ for s in stages],
    }
    archive.record("signoff", {
        "verdict": verdict, "score": report.score, "grade": report.grade,
        "module": report.module,
        "stages": {s.name: s.status for s in stages},
    })
    return result
