"""Code coverage — which RTL do the tests actually reach?

Mutation coverage says the suite catches the faults we inject. Code coverage
says which lines it exercises at all. They answer different questions and
disagree in useful ways: a line no test reaches cannot host a caught mutant, so
an unreached line is a blind spot that mutation testing will report as a
*survivor* only if a mutation operator happens to target it.

Verilator instruments per-line when built with `--coverage`. The run needs its
own SIM_BUILD for the same reason every other configured run does — cocotb does
not treat EXTRA_ARGS as a build dependency, so sharing a build directory
silently reuses a model compiled without instrumentation and reports a coverage
result for a binary that was never instrumented.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import rtl_qor
from .config import sim_env

_ROOT = Path(__file__).resolve().parents[1]
_TB = _ROOT / "tb"

# `verilator_coverage --annotate` prefixes a line with `%` when ANY point
# attached to it is unhit, followed by the execution count. `%000000` means the
# line never ran at all; `%000005` means it ran but some branch on it did not.
# Reporting only the first kind misses most of what the summary counts.
_ANNOT_RE = re.compile(r"^%(?P<count>\d+)\s(?P<text>.*)$")

# The elaboration guards live in a `translate_off` block and are *supposed* to
# stay untaken — they fire only on an illegal parameterisation. Counting them as
# a gap would mean the only route to 100% is to break the design. Detected by
# range rather than by matching text, so every line of the block is covered by
# the exemption, not just the ones that happen to mention `$error`.
_OFF_RE = re.compile(r"//\s*synthesis\s+translate_off")
_ON_RE = re.compile(r"//\s*synthesis\s+translate_on")


def _exempt_lines(source_path: Path) -> set:
    out, inside = set(), False
    try:
        text = source_path.read_text(errors="replace")
    except OSError:
        return out
    for n, line in enumerate(text.splitlines(), 1):
        if _OFF_RE.search(line):
            inside = True
        if inside:
            out.add(n)
        if _ON_RE.search(line):
            inside = False
    return out
_SUMMARY_RE = re.compile(
    r"lines with all attached points covered\s*:\s*(?P<pct>[\d.]+)%\s*\(\s*"
    r"(?P<hit>\d+)/\s*(?P<total>\d+)\)")


@dataclass
class UncoveredLine:
    line: int
    text: str
    count: int          # 0 = never executed; >0 = executed, some branch unhit
    expected: bool      # an elaboration guard that must never fire

    def to_dict(self) -> dict:
        return {"line": self.line, "text": self.text.strip(), "count": self.count,
                "kind": "never-executed" if self.count == 0 else "partial",
                "expected_unreachable": self.expected}


def available() -> bool:
    return (rtl_qor.verilator_available()
            and shutil.which("verilator_coverage") is not None)


def run(*, bp_profile: str = "single", timeout: int = 600,
        source: str = "rtl/gamma.v") -> dict:
    """Run the regression instrumented, then annotate the result.

    Returns the covered percentage and — the part worth acting on — the exact
    lines no test reached.
    """
    if not available():
        return {"available": False,
                "error": "verilator / verilator_coverage not on PATH"}

    dat = _TB / "coverage.dat"
    if dat.exists():
        dat.unlink()
    try:
        sim = subprocess.run(
            ["make", "-s", "SIM=verilator", "SIM_BUILD=sim_build_cov",
             "EXTRA_ARGS=--coverage -O3"],
            cwd=str(_TB), env=sim_env(BP_PROFILE=bp_profile),
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"regression timed out after {timeout}s"}
    if not dat.exists():
        tail = (sim.stdout + sim.stderr).strip().splitlines()[-1:] or [""]
        return {"available": True,
                "error": f"no coverage.dat produced — {tail[0][:160]}"}

    with tempfile.TemporaryDirectory() as td:
        try:
            ann = subprocess.run(
                ["verilator_coverage", "--annotate", td, "--annotate-all",
                 str(dat)],
                cwd=str(_TB), env=sim_env(), capture_output=True, text=True,
                timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": True, "error": str(exc)}

        m = _SUMMARY_RE.search(ann.stdout + ann.stderr)
        annotated = Path(td) / Path(source).name
        exempt = _exempt_lines(_ROOT / source)
        uncovered: List[UncoveredLine] = []
        if annotated.exists():
            for n, raw in enumerate(annotated.read_text(errors="replace").splitlines(), 1):
                um = _ANNOT_RE.match(raw)
                if not um:
                    continue
                text = um["text"]
                uncovered.append(UncoveredLine(
                    line=n, text=text, count=int(um["count"]), expected=n in exempt))

    return {
        "available": True,
        "source": source,
        "percent": float(m["pct"]) if m else None,
        "covered": int(m["hit"]) if m else None,
        "points": int(m["total"]) if m else None,
        "uncovered": [u.to_dict() for u in uncovered],
        # The number to act on: gaps that are not an elaboration guard.
        "actionable": [u.to_dict() for u in uncovered if not u.expected],
        "note": ("Line coverage under the default elaboration. A `generate` "
                 "branch that is not selected does not appear at all — it is "
                 "not reported as uncovered, it is absent. That is why the "
                 "sign-off gate runs the LUT_SYNC_READ=1 configuration "
                 "separately rather than trusting a percentage here. "
                 "`never-executed` is the signal worth acting on; `partial` "
                 "often reflects how Verilator attributes branch points to "
                 "declaration lines, which is coarser than it looks."),
    }
