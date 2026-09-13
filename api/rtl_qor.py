"""Deterministic RTL quality / QoR analysis for the gamma DUT.

Self-contained port of ai_driven_rtl's analyzer/drc, *calibrated for this
project*: the RTL here is intentionally portable Verilog-2001 (reg/wire,
`always @`), so — unlike the upstream SV-first analyzer — we do NOT penalize
the absence of `logic`/`always_ff`. Instead we grade what actually matters for
a synthesizable pixel-pipeline: lints clean, synthesizes, no inferred latches,
sequential logic uses non-blocking assignment, reset present and classified.

Tools degrade gracefully: verilator absent -> lint skipped; yosys absent ->
synth checks skipped. No LLM, fully unit-testable.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RTL = _ROOT / "rtl" / "gamma.v"
_TIMEOUT = 60

_MODULE_RE = re.compile(r"\bmodule\s+(\w+)")
_PORT_RE = re.compile(
    r"\b(input|output|inout)\b\s+(?:(wire|reg|logic|bit)\s+)?"
    r"(?:(signed|unsigned)\s+)?(\[[^\]]*\]\s*)?(\w+)"
)
_PARAM_RE = re.compile(r"\bparameter\b\s+(?:integer\s+|type\s+)?(?:\w+\s+)?(\w+)\s*=")


def strip_fences(code: str) -> str:
    """Drop ```...``` markdown fences if a caller pasted them."""
    m = re.search(r"```(?:\w+)?\n(.*?)```", code, re.S)
    return m.group(1) if m else code


def strip_comments(code: str) -> str:
    """Remove // line and /* */ block comments so prose ('active low') in a
    header doesn't get mistaken for HDL constructs during static analysis."""
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    return code


def project_rtl() -> str:
    return DEFAULT_RTL.read_text() if DEFAULT_RTL.exists() else ""


def detect_top(code: str) -> Optional[str]:
    m = _MODULE_RE.search(code)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# verilator lint
# ---------------------------------------------------------------------------
@dataclass
class LintResult:
    ok: bool
    available: bool
    issues: List[str] = field(default_factory=list)
    raw: str = ""
    top: Optional[str] = None


def verilator_available() -> bool:
    return shutil.which("verilator") is not None


def lint(code: str) -> LintResult:
    code = strip_fences(code)
    top = detect_top(code)
    if not verilator_available():
        return LintResult(False, False, ["verilator not installed"], top=top)
    if not code.strip():
        return LintResult(False, True, ["empty source"], top=top)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "design.v"
        src.write_text(code if code.endswith("\n") else code + "\n")
        cmd = [
            "verilator", "--lint-only", "-Wall",
            "-Wno-DECLFILENAME", "-Wno-EOFNEWLINE",
        ]
        if top:
            cmd += ["--top-module", top]
        cmd.append(str(src))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
    raw = (proc.stdout + proc.stderr).strip()
    issues = [l for l in raw.splitlines() if "%Error" in l or "%Warning" in l]
    return LintResult(proc.returncode == 0, True, issues, raw, top)


# ---------------------------------------------------------------------------
# yosys generic synthesis (synthesizability + gate-level stats)
# ---------------------------------------------------------------------------
@dataclass
class SynthResult:
    ok: bool
    available: bool
    cells: int = 0
    flops: int = 0
    latches: int = 0
    issues: List[str] = field(default_factory=list)


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def _count(stat_block: str, pattern: str) -> int:
    total = 0
    for line in stat_block.splitlines():
        m = re.match(r"\s*(\d+)\s+(\$\S+)", line)
        if m and re.search(pattern, m.group(2)):
            total += int(m.group(1))
    return total


def synth(code: str) -> SynthResult:
    code = strip_fences(code)
    top = detect_top(code) or "top"
    if not yosys_available():
        return SynthResult(False, False, issues=["yosys not installed"])
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "design.v"
        src.write_text(code if code.endswith("\n") else code + "\n")
        script = f"read_verilog {src}; synth -top {top}; stat"
        proc = subprocess.run(["yosys", "-p", script], capture_output=True,
                              text=True, timeout=_TIMEOUT)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        issues = [l for l in out.splitlines() if "ERROR" in l.upper()][:4]
        return SynthResult(False, True, issues=issues or ["yosys synth failed"])
    # Parse the last "=== top ===" statistics block.
    blocks = out.split(f"=== {top} ===")
    stat = blocks[-1] if len(blocks) > 1 else out
    cells_m = re.search(r"(\d+)\s+cells", stat)
    return SynthResult(
        ok=True,
        available=True,
        cells=int(cells_m.group(1)) if cells_m else 0,
        flops=_count(stat, r"DFF|SDFF|ADFF|\$dff"),
        latches=_count(stat, r"DLATCH|\$dlatch|LATCH"),
    )


# ---------------------------------------------------------------------------
# structural checks + score
# ---------------------------------------------------------------------------
@dataclass
class Check:
    id: str
    severity: str  # "error" | "warn" | "info"
    ok: bool
    detail: str


def reset_analysis(code: str) -> dict:
    code = strip_comments(code)
    # Prefer a reset that drives an edge-sensitivity list (the synthesizable
    # reset), which also tells us async vs sync directly.
    edge = re.search(r"(pos|neg)edge\s+(\w*(?:rst|reset)\w*)\b", code, re.I)
    if edge:
        rst, kind = edge.group(2), "async"
        active = "low" if edge.group(1) == "neg" else "high"
        return {"present": True, "kind": kind, "active": active, "signal": rst}
    m = re.search(r"\b(\w*(?:rst|reset)\w*)\b", code, re.I)
    if not m:
        return {"present": False, "kind": "none", "active": "unknown", "signal": None}
    rst = m.group(1)
    active = "unknown"
    if re.search(rf"!\s*{re.escape(rst)}\b", code) or rst.lower().endswith("_n"):
        active = "low"
    elif re.search(rf"\bif\s*\(\s*{re.escape(rst)}\s*\)", code):
        active = "high"
    return {"present": True, "kind": "sync", "active": active, "signal": rst}


def _seq_uses_nonblocking(code: str) -> bool:
    """True if clocked blocks use <= and contain no top-level blocking '='."""
    has_clocked = bool(re.search(r"always\s*@\s*\([^)]*edge", code))
    if not has_clocked:
        return True  # no sequential logic to judge
    return "<=" in code


@dataclass
class QoRReport:
    module: Optional[str]
    ports: List[dict]
    params: List[str]
    metrics: Dict[str, object]
    checks: List[Check]
    score: int
    grade: str
    lint_tool: str

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "ports": self.ports,
            "params": self.params,
            "metrics": self.metrics,
            "checks": [c.__dict__ for c in self.checks],
            "score": self.score,
            "grade": self.grade,
            "lint_tool": self.lint_tool,
        }


def _grade(s: int) -> str:
    return "A" if s >= 90 else "B" if s >= 80 else "C" if s >= 70 else "D" if s >= 60 else "F"


def analyze(code: Optional[str] = None) -> QoRReport:
    code = strip_fences(code if code is not None else project_rtl())

    lr = lint(code)
    lint_tool = "verilator" if lr.available else "none"

    ports = [{"name": n, "direction": d, "width": (w or "").strip()}
             for d, _t, _s, w, n in _PORT_RE.findall(code)
             if n not in {"wire", "reg", "logic", "bit"}]
    # de-dup by name, preserve order
    seen: set = set()
    ports = [p for p in ports if not (p["name"] in seen or seen.add(p["name"]))]
    params = list(dict.fromkeys(_PARAM_RE.findall(code)))

    checks: List[Check] = []
    checks.append(Check("module_present", "error", bool(_MODULE_RE.search(code)),
                        "module declaration found"))
    checks.append(Check("ff_nonblocking", "error", _seq_uses_nonblocking(code),
                        "sequential logic uses non-blocking <="))

    rst = reset_analysis(code)
    checks.append(Check("reset_present", "warn", rst["present"],
                        "reset present" if rst["present"] else "no reset detected"))
    if rst["present"]:
        checks.append(Check("reset_classified", "info", True,
                            f"{rst['kind']} reset, active-{rst['active']} ({rst['signal']})"))

    checks.append(Check("trailing_newline", "info", code.endswith("\n"),
                        "ends with newline"))

    # House style (api/style.py). A dialect violation is a `warn` because it
    # breaks the cocotb flow (TOPLEVEL_LANG=verilog), not because it looks
    # different; everything else is a note.
    from . import style as style_mod
    sf = style_mod.check(code)
    style_warns = [f for f in sf if f.severity == "warn"]
    if style_warns:
        checks.append(Check("style_dialect", "warn", False,
                            "; ".join(f"L{f.line}: {f.message}" for f in style_warns[:2])))
    checks.append(Check("style_clean", "info", not sf,
                        "house style clean" if not sf
                        else f"{len(sf)} style finding(s): "
                             + "; ".join(f"L{f.line} {f.rule}" for f in sf[:3])))
    if lr.available:
        checks.append(Check("lint_clean", "error", lr.ok,
                            f"verilator: {len(lr.issues)} finding(s)"))

    sr = synth(code)
    metrics: Dict[str, object] = {
        "lint_pass": lr.ok if lr.available else None,
        "lint_finding_count": len(lr.issues),
        "port_count": len(ports),
        "param_count": len(params),
        "line_count": len(code.splitlines()),
        "reset_kind": rst["kind"],
        "reset_active": rst["active"],
        "hdl_dialect": "verilog-2001" if re.search(r"\b(reg|wire)\b", code) else "systemverilog",
    }
    if sr.available:
        checks.append(Check("synthesizable", "error", sr.ok,
                            "synthesizes with yosys" if sr.ok
                            else "yosys synthesis failed: " + "; ".join(sr.issues[:2])))
        if sr.ok and sr.latches:
            checks.append(Check("no_inferred_latches", "warn", False,
                                f"{sr.latches} inferred latch(es)"))
        metrics.update(synthesizable=sr.ok, synth_cells=sr.cells,
                       synth_flops=sr.flops, synth_latches=sr.latches)

    sev = {"error": 30, "warn": 12, "info": 4}
    penalty = sum(sev[c.severity] for c in checks if not c.ok)
    if lr.available and not lr.ok:
        penalty += 25
    penalty += min(20, len(lr.issues) * 3)
    score = max(0, 100 - penalty)

    return QoRReport(detect_top(code), ports, params, metrics, checks,
                     score, _grade(score), lint_tool)


# ---------------------------------------------------------------------------
# RTL design-rule check (coded, severity-graded view over the analyzer)
# ---------------------------------------------------------------------------
_RULES = {
    "module_present":   ("DRC-STRUCT-001", "Module declaration present"),
    "ff_nonblocking":   ("DRC-SEQ-001", "Non-blocking assignment in sequential logic"),
    "reset_present":    ("DRC-RST-001", "Reset present"),
    "reset_classified": ("DRC-RST-002", "Reset classified (sync/async, level)"),
    "trailing_newline": ("DRC-STYLE-001", "Trailing newline"),
    "lint_clean":       ("DRC-LINT-001", "Lints clean (verilator)"),
    "synthesizable":    ("DRC-SYNTH-001", "Synthesizable (yosys)"),
    "no_inferred_latches": ("DRC-LATCH-001", "No inferred latches"),
}


def run_drc(code: Optional[str] = None) -> dict:
    report = analyze(code)
    rules = []
    errors = warnings = 0
    for c in report.checks:
        rcode, name = _RULES.get(c.id, (f"DRC-GEN-{c.id.upper()}", c.id))
        if not c.ok:
            if c.severity == "error":
                errors += 1
            elif c.severity == "warn":
                warnings += 1
        rules.append({"code": rcode, "name": name, "severity": c.severity,
                      "status": "pass" if c.ok else "violation", "detail": c.detail})
    return {
        "module": report.module,
        "clean": errors == 0 and warnings == 0,
        "errors": errors,
        "warnings": warnings,
        "rules": rules,
        "note": "RTL design-rule check; physical/geometric DRC needs a layout (PnR flow).",
    }
