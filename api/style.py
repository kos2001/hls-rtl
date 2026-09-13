"""House style checks for this repository's RTL.

Why not Verible
---------------
Verible is the tool for SystemVerilog style, and it is not packaged for this
platform — closing the gap with it means installing a release binary by hand and
then maintaining that by hand. It also enforces a *generic* SystemVerilog style
guide, and this codebase deliberately is not generic SystemVerilog: `gamma.v` is
portable Verilog-2001 on purpose, so a stock ruleset spends its output telling
you to use `logic` and `always_ff` — advice this project has an explicit reason
to refuse. Rules that fight the codebase get muted, and a muted linter checks
nothing.

So these encode what this repo actually promises, taken from `CLAUDE.md`,
`docs/UARCH.md` and the RTL's own header. Each rule cites the convention it
enforces, because a style rule nobody can trace to a decision is one that will
be argued with rather than followed.

Severity is `note` throughout, with one exception: a dialect violation is a
`warn`, because it breaks the cocotb flow (`TOPLEVEL_LANG=verilog`) rather than
merely looking different.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

# SystemVerilog constructs that would break the Verilog-2001 contract. The flow
# runs TOPLEVEL_LANG=verilog and the SystemC/golden mirrors assume this dialect,
# so these are not a matter of taste.
_SV_ONLY = (
    (r"\blogic\b", "`logic` is SystemVerilog; this module is Verilog-2001 (`reg`/`wire`)"),
    (r"\balways_ff\b", "`always_ff` is SystemVerilog; use `always @(posedge ...)`"),
    (r"\balways_comb\b", "`always_comb` is SystemVerilog; use `always @*`"),
    (r"\balways_latch\b", "`always_latch` is SystemVerilog"),
    (r"\binterface\b\s+\w+\s*;", "SystemVerilog interfaces are not used in this flow"),
    (r"\bpackage\b\s+\w+\s*;", "SystemVerilog packages are not used in this flow"),
)


@dataclass
class StyleFinding:
    rule: str
    severity: str        # "warn" | "note"
    line: int
    text: str
    message: str
    convention: str      # where the rule comes from

    def to_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "line": self.line,
                "text": self.text.strip()[:100], "message": self.message,
                "convention": self.convention}


def _code_lines(code: str) -> List[Tuple[int, str]]:
    """Line numbers and text with comments and string literals removed.

    A rule that fires on the word `logic` inside a comment explaining why the
    module does not use `logic` would be actively counterproductive.
    """
    out: List[Tuple[int, str]] = []
    in_block = False
    for n, raw in enumerate(code.splitlines(), 1):
        line = raw
        if in_block:
            end = line.find("*/")
            if end < 0:
                continue
            line, in_block = line[end + 2:], False
        while "/*" in line:
            start = line.find("/*")
            end = line.find("*/", start + 2)
            if end < 0:
                line, in_block = line[:start], True
                break
            line = line[:start] + line[end + 2:]
        line = line.split("//")[0]
        line = re.sub(r'"[^"]*"', '""', line)
        if line.strip():
            out.append((n, line))
    return out


def _rule_dialect(code: str) -> List[StyleFinding]:
    out = []
    for n, text in _code_lines(code):
        for pat, msg in _SV_ONLY:
            if re.search(pat, text):
                out.append(StyleFinding(
                    "STYLE-DIALECT", "warn", n, text, msg,
                    "CLAUDE.md: portable Verilog-2001, TOPLEVEL_LANG=verilog"))
    return out


def _rule_tabs(code: str) -> List[StyleFinding]:
    return [StyleFinding("STYLE-TABS", "note", n, text,
                         "tab character; this file is space-indented",
                         "consistency with the existing source")
            for n, text in enumerate(code.splitlines(), 1) if "\t" in text]


def _rule_line_length(code: str, limit: int = 100) -> List[StyleFinding]:
    return [StyleFinding("STYLE-WIDTH", "note", n, text,
                         f"{len(text)} columns (limit {limit})",
                         "reviewable side-by-side diffs")
            for n, text in enumerate(code.splitlines(), 1) if len(text) > limit]


def _rule_trailing_ws(code: str) -> List[StyleFinding]:
    return [StyleFinding("STYLE-TRAILWS", "note", n, text,
                         "trailing whitespace",
                         "keeps diffs free of invisible changes")
            for n, text in enumerate(code.splitlines(), 1)
            if text != text.rstrip() and text.strip()]


def _rule_naming(code: str) -> List[StyleFinding]:
    """Signals lower_snake_case, parameters and localparams ALL_CAPS.

    Not cosmetic here: `api/waveform.py` tells elaboration parameters apart from
    signals by exactly this convention, so a lower-case parameter is drawn as a
    waveform and an upper-case signal disappears from the viewer.
    """
    out: List[StyleFinding] = []
    decl = re.compile(
        r"^\s*(?:(?P<param>parameter|localparam)(?:\s+integer)?|"
        r"(?P<sig>reg|wire)(?:\s+signed)?)\s*(?:\[[^\]]*\]\s*)?(?P<name>[A-Za-z_]\w*)")
    for n, text in _code_lines(code):
        m = decl.match(text)
        if not m:
            continue
        name = m["name"]
        if m["param"]:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                out.append(StyleFinding(
                    "STYLE-NAMING", "note", n, text,
                    f"parameter `{name}` is not ALL_CAPS",
                    "api/waveform.py separates parameters from signals by case"))
        elif m["sig"] and re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            out.append(StyleFinding(
                "STYLE-NAMING", "note", n, text,
                f"signal `{name}` is ALL_CAPS and will be read as a parameter",
                "api/waveform.py separates parameters from signals by case"))
    return out


def _rule_header(code: str) -> List[StyleFinding]:
    """The module must open with a comment block stating its contract.

    `api/server.py::_design_digest` and the knowledge base both quote that
    header as the design's stated contract; a module without one is a module
    whose contract the agent cannot cite.
    """
    first = next((l for l in code.splitlines() if l.strip()), "")
    if first.startswith("//"):
        return []
    return [StyleFinding("STYLE-HEADER", "note", 1, first,
                         "no leading comment block stating the module contract",
                         "the contract header is quoted into agent grounding")]


def _rule_default_nettype(code: str) -> List[StyleFinding]:
    """`default_nettype none` catches typo'd signal names at elaboration."""
    if re.search(r"`default_nettype\s+none", code):
        return []
    return [StyleFinding("STYLE-NETTYPE", "note", 1, "",
                         "no `default_nettype none`; a typo'd name silently "
                         "becomes an implicit wire",
                         "rtl/gamma.v sets it; keep new modules consistent")]


_RULES: Tuple[Callable[[str], List[StyleFinding]], ...] = (
    _rule_dialect, _rule_tabs, _rule_line_length, _rule_trailing_ws,
    _rule_naming, _rule_header, _rule_default_nettype,
)


def check(code: str) -> List[StyleFinding]:
    out: List[StyleFinding] = []
    for rule in _RULES:
        out.extend(rule(code))
    return sorted(out, key=lambda f: (f.line, f.rule))


def report(code: Optional[str] = None) -> dict:
    from . import rtl_qor
    src = rtl_qor.strip_fences(code if code is not None else rtl_qor.project_rtl())
    findings = check(src)
    warns = [f for f in findings if f.severity == "warn"]
    return {
        "clean": not findings,
        "warnings": len(warns),
        "notes": len(findings) - len(warns),
        "findings": [f.to_dict() for f in findings],
        "note": ("House style for THIS repository, not a generic SystemVerilog "
                 "guide: a stock ruleset would spend its output asking for "
                 "`logic` and `always_ff`, which this flow refuses on purpose. "
                 "Each rule cites the convention it enforces."),
    }
