"""Mutation coverage — does the gate actually CATCH a bug?

A passing scoreboard says the design agrees with the golden model on the inputs
someone thought to write down. It says nothing about sensitivity: whether the
suite would notice if the design were wrong. Pass rate and detection power are
different quantities, and only one of them is usually measured.

This injects plausible faults one at a time and runs the real gate
(`api/improve.py::prove`) on each. A mutant that survives is not a hypothetical
— it is a concrete edit to the RTL that every check in this repository accepts.

Why not MCY
-----------
YosysHQ's MCY is the tool for this and it is worth using. It also builds its own
equivalence flow, which would measure *that* flow rather than this one. The
interesting result in this project is already known to be flow-specific: an
effective FIFO depth of 7 survives the scoreboard entirely and is caught only by
the formal stage. Measuring the gate that actually gates is the point, so the
harness drives `prove()` and reports WHICH stage caught each mutant.

Cost
----
The gate takes ~25s, so a run is minutes, not seconds. Stages stop at the first
one that catches a mutant, which is also what makes "caught by" meaningful:
whatever reports the fault first is the cheapest thing that could have found it.

Mutants are proved in SEQUENCE, deliberately. The gate's stages share
`build/sc_out.txt`, the SystemC binary and `tb/`, so parallel proofs interfere
and produce verdicts that belong to neither candidate. Running a campaign
alongside any other `prove()` has the same effect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import improve

_ROOT = Path(__file__).resolve().parents[1]
_RTL = _ROOT / "rtl" / "gamma.v"

# Order matters only for reporting; each stage is the first that can see a fault.
STAGE_ORDER = ("lint", "design", "synthesize", "systemc", "simulate",
               "configs", "4state", "formal")


@dataclass
class Mutant:
    id: str
    operator: str          # which fault class
    description: str       # what changed, in words
    line: int
    before: str
    after: str
    code: str = field(repr=False, default="")

    def to_dict(self, include_code: bool = False) -> dict:
        d = {"id": self.id, "operator": self.operator,
             "description": self.description, "line": self.line,
             "before": self.before.strip(), "after": self.after.strip()}
        if include_code:
            d["code"] = self.code
        return d


def _code_lines(src: str) -> List[Tuple[int, str]]:
    """Line numbers and text for lines that are actual code.

    Comments and the `translate_off` guard block are skipped: mutating a comment
    produces a mutant that is textually different and functionally identical,
    which would silently inflate the survival rate with noise.
    """
    out: List[Tuple[int, str]] = []
    in_guard = False
    for n, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if "synthesis translate_off" in stripped:
            in_guard = True
        elif "synthesis translate_on" in stripped:
            in_guard = False
            continue
        if in_guard or not stripped or stripped.startswith("//"):
            continue
        # drop a trailing comment so operators do not match inside it
        out.append((n, line.split("//")[0]))
    return out


# --- fault classes -----------------------------------------------------------
# Each returns (label, pattern, replacement) applied to ONE occurrence at a time.

_TOKEN_SWAPS: Tuple[Tuple[str, str, str, str], ...] = (
    ("relational", r"!=", "==", "inverted a comparison"),
    ("relational", r"==", "!=", "inverted a comparison"),
    ("arithmetic", r"\+", "-", "turned an addition into a subtraction"),
    ("arithmetic", r"(?<![<>=!])-(?!>)", "+", "turned a subtraction into an addition"),
    ("boolean", r"&&", "||", "weakened a conjunction to a disjunction"),
    ("boolean", r"(?<![&])&(?![&])", "|", "turned a bitwise AND into an OR"),
)


# `[PIXEL_W-1:0]`, `{CNT_W{1'b0}}` and friends: the `-1` is a width idiom, not a
# computation the design performs. Mutating it exercises the toolchain's width
# rules rather than the DUT, and there are enough of them to dominate the set.
_RANGE_SPANS_RE = re.compile(r"\[[^\]]*\]|\{[^{}]*\{[^{}]*\}[^{}]*\}")


def _in_width_idiom(text: str, pos: int) -> bool:
    return any(m.start() <= pos < m.end() for m in _RANGE_SPANS_RE.finditer(text))


def _swap_mutants(src: str) -> List[Mutant]:
    out: List[Mutant] = []
    for lineno, text in _code_lines(src):
        for op, pat, repl, desc in _TOKEN_SWAPS:
            for m in re.finditer(pat, text):
                if _in_width_idiom(text, m.start()):
                    continue
                new_line = text[:m.start()] + repl + text[m.end():]
                if new_line == text:
                    continue
                out.append(Mutant(
                    id=f"{op}-{lineno}-{m.start()}", operator=op, description=desc,
                    line=lineno, before=text, after=new_line,
                    code=_replace_line(src, lineno, new_line)))
    return out


def _offbyone_mutants(src: str) -> List[Mutant]:
    """Perturb a bound by one. The fault class that motivated all of this: an
    effective FIFO depth of 7 instead of 8 survives the whole scoreboard."""
    out: List[Mutant] = []
    for lineno, text in _code_lines(src):
        for name in ("CNT_MAX", "PTR_MAX", "FIFO_DEPTH", "DEPTH_M1"):
            for m in re.finditer(rf"\b{name}\b", text):
                if "localparam" in text or "parameter" in text:
                    continue  # that is a redefinition, not an off-by-one at a use
                new_line = f"{text[:m.start()]}({name} - 1'b1){text[m.end():]}"
                out.append(Mutant(
                    id=f"offbyone-{lineno}-{m.start()}", operator="off-by-one",
                    description=f"reduced {name} by one at its use",
                    line=lineno, before=text, after=new_line,
                    code=_replace_line(src, lineno, new_line)))
    return out


def _stuck_mutants(src: str) -> List[Mutant]:
    """Force a control signal to a constant — the classic stuck-at fault."""
    out: List[Mutant] = []
    for lineno, text in _code_lines(src):
        m = re.match(r"^(\s*assign\s+([A-Za-z_]\w*)\s*=\s*)(.+?);\s*$", text)
        if not m:
            continue
        for const in ("1'b0", "1'b1"):
            new_line = f"{m.group(1)}{const};"
            out.append(Mutant(
                id=f"stuck-{lineno}-{const[-1]}", operator="stuck-at",
                description=f"tied {m.group(2)} to {const}",
                line=lineno, before=text, after=new_line,
                code=_replace_line(src, lineno, new_line)))
    return out


def _drop_mutants(src: str) -> List[Mutant]:
    """Delete a single non-blocking assignment — a forgotten update or a reset
    branch that fails to clear."""
    out: List[Mutant] = []
    for lineno, text in _code_lines(src):
        if "<=" not in text or text.strip().startswith("//"):
            continue
        if not re.match(r"^\s*[A-Za-z_]\w*(\[[^\]]*\])?\s*<=", text):
            continue
        out.append(Mutant(
            id=f"drop-{lineno}", operator="dropped-update",
            description="deleted a register update",
            line=lineno, before=text, after="(deleted)",
            code=_delete_line(src, lineno)))
    return out


def _channel_mutants(src: str) -> List[Mutant]:
    """Cross two channels. Invisible when the LUTs are identical, which is
    exactly why the test set uses a different gamma per channel."""
    out: List[Mutant] = []
    pairs = (("lut_r_mem", "lut_b_mem"), ("lut_g_mem", "lut_r_mem"))
    for lineno, text in _code_lines(src):
        for a, b in pairs:
            if f"{a}[" not in text:
                continue
            new_line = text.replace(f"{a}[", f"{b}[", 1)
            out.append(Mutant(
                id=f"channel-{lineno}-{a}", operator="channel-cross",
                description=f"read {b} where {a} was intended",
                line=lineno, before=text, after=new_line,
                code=_replace_line(src, lineno, new_line)))
    return out


_GENERATORS: Tuple[Callable[[str], List[Mutant]], ...] = (
    _swap_mutants, _offbyone_mutants, _stuck_mutants, _drop_mutants, _channel_mutants,
)


def _replace_line(src: str, lineno: int, new_line: str) -> str:
    lines = src.splitlines()
    lines[lineno - 1] = new_line
    return "\n".join(lines) + "\n"


def _delete_line(src: str, lineno: int) -> str:
    lines = src.splitlines()
    del lines[lineno - 1]
    return "\n".join(lines) + "\n"


def generate(source: Optional[str] = None, *, limit: int = 0) -> List[Mutant]:
    """Every distinct single-fault mutant, deterministically ordered.

    Deduplicated by resulting source text: different operators can land on the
    same program (`!=` swapped twice, say), and counting one program twice would
    distort the survival rate.
    """
    src = source if source is not None else _RTL.read_text()
    seen: Dict[str, Mutant] = {}
    for gen in _GENERATORS:
        for mut in gen(src):
            if mut.code == src or mut.code in seen:
                continue
            seen[mut.code] = mut
    mutants = sorted(seen.values(), key=lambda m: (m.operator, m.line, m.id))
    return mutants[:limit] if limit else mutants


@dataclass
class MutantResult:
    mutant: Mutant
    caught: bool
    caught_by: Optional[str]
    detail: str
    elapsed_s: float

    def to_dict(self) -> dict:
        return {**self.mutant.to_dict(), "caught": self.caught,
                "caught_by": self.caught_by, "detail": self.detail,
                "elapsed_s": round(self.elapsed_s, 1)}


def run(*, limit: int = 12, timeout: int = 600, operators: Optional[List[str]] = None,
        bp_profile: str = "single") -> dict:
    """Inject each mutant and report whether the gate catches it.

    `limit` exists because the gate is ~17s per mutant; the full set is a
    nightly job, not an interactive one.
    """
    mutants = generate()
    if operators:
        mutants = [m for m in mutants if m.operator in operators]
    total_available = len(mutants)
    mutants = mutants[:limit] if limit else mutants

    results: List[MutantResult] = []
    for mut in mutants:
        proof = improve.prove(mut.code, name=f"mut-{mut.id}",
                              timeout=timeout, bp_profile=bp_profile)
        caught_by = next((s for s in STAGE_ORDER if proof.stages.get(s) == "fail"), None)
        results.append(MutantResult(
            mutant=mut, caught=caught_by is not None, caught_by=caught_by,
            detail=proof.details.get(caught_by, "") if caught_by else
                   "survived every stage", elapsed_s=proof.elapsed_s))

    caught = [r for r in results if r.caught]
    survived = [r for r in results if not r.caught]
    by_stage: Dict[str, int] = {}
    for r in caught:
        by_stage[r.caught_by or "?"] = by_stage.get(r.caught_by or "?", 0) + 1

    return {
        "total_available": total_available,
        "run": len(results),
        "caught": len(caught),
        "survived": len(survived),
        "score": round(100 * len(caught) / len(results)) if results else 0,
        "caught_by_stage": by_stage,
        "operators": sorted({m.operator for m in mutants}),
        "results": [r.to_dict() for r in results],
        "note": ("A surviving mutant is a concrete edit to rtl/gamma.v that every "
                 "check in this repository accepts. It is a gap in detection "
                 "power, not necessarily a bug in the design — but it is the "
                 "shape of bug this suite would miss."),
    }


def preview(limit: int = 0) -> dict:
    """The mutant set without running anything — cheap, for inspecting coverage
    of the fault classes before paying for a run."""
    mutants = generate(limit=limit)
    by_op: Dict[str, int] = {}
    for m in mutants:
        by_op[m.operator] = by_op.get(m.operator, 0) + 1
    return {"total": len(mutants), "by_operator": by_op,
            "mutants": [m.to_dict() for m in mutants]}
