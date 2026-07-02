"""RTL segment traceability (improvement #3, IncreRTL-style).

ai_driven_rtl's incremental.py diffs RTL as plain text and re-prompts the LLM.
IncreRTL's contribution is structural: parse the RTL into syntax-preserving
blocks (ports, params, declarations, always/assign), so a requirement change
maps to the *specific segments* it affects and only those are regenerated —
preserving the surrounding code's structure and style.

This is a pragmatic line/brace-aware segmenter (not a full Verilog front end):
it tracks begin/end nesting for procedural blocks and classifies the rest by
construct. Good enough to localize a diff to segments for selective regen; for
deeper analysis the yosys netlist path (see rtl_qor.synth) is available.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Segment:
    id: int
    kind: str            # module_header | param | port | decl | always | assign | initial | other
    name: Optional[str]
    start_line: int      # 1-based, inclusive
    end_line: int

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "name": self.name,
                "start_line": self.start_line, "end_line": self.end_line}


_ALWAYS_RE = re.compile(r"\balways\b")
_INITIAL_RE = re.compile(r"\binitial\b")
_PORT_RE = re.compile(r"^\s*(input|output|inout)\b")
_DECL_RE = re.compile(r"^\s*(reg|wire|logic|localparam|parameter)\b")
_ASSIGN_RE = re.compile(r"^\s*assign\b")
_MODULE_RE = re.compile(r"^\s*module\b")
_NAME_AFTER = re.compile(r"\b(reg|wire|logic|localparam|parameter|module)\b\s+(?:\[[^\]]*\]\s*)?(?:integer\s+|signed\s+|\[[^\]]*\]\s*)?(\w+)")


def _count_tokens(line: str) -> tuple:
    # crude: count begin/end words not inside // comments
    code = re.sub(r"//.*$", "", line)
    return len(re.findall(r"\bbegin\b", code)), len(re.findall(r"\bend\b", code))


def segment(code: str) -> List[Segment]:
    lines = code.splitlines()
    segs: List[Segment] = []
    i = 0
    sid = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*") \
                or stripped.startswith("*") or stripped == "`default_nettype none" \
                or stripped == "`default_nettype wire":
            i += 1
            continue

        # Procedural block: always / initial — span to matching end at depth 0.
        if _ALWAYS_RE.search(line) or _INITIAL_RE.search(line):
            kind = "always" if _ALWAYS_RE.search(line) else "initial"
            start = i
            depth = 0
            seen_begin = False
            j = i
            while j < n:
                b, e = _count_tokens(lines[j])
                depth += b - e
                if b:
                    seen_begin = True
                # single-statement always with no begin: ends at first ';'
                if not seen_begin and ";" in re.sub(r"//.*$", "", lines[j]) and j > i:
                    break
                if seen_begin and depth <= 0 and j >= i:
                    break
                j += 1
            segs.append(Segment(sid, kind, None, start + 1, j + 1))
            sid += 1
            i = j + 1
            continue

        if _MODULE_RE.search(line):
            kind = "module_header"
        elif _PORT_RE.search(line):
            kind = "port"
        elif _ASSIGN_RE.search(line):
            kind = "assign"
        elif _DECL_RE.search(line):
            kind = "param" if re.search(r"\b(localparam|parameter)\b", line) else "decl"
        else:
            kind = "other"
        nm = _NAME_AFTER.search(line)
        name = nm.group(2) if nm else None
        # a declaration/port may span until ';'
        end = i
        if ";" not in re.sub(r"//.*$", "", line) and kind in ("decl", "param", "port", "assign", "module_header"):
            k = i
            while k < n and ";" not in re.sub(r"//.*$", "", lines[k]) and ")" not in lines[k]:
                k += 1
            end = min(k, n - 1)
        segs.append(Segment(sid, kind, name, i + 1, end + 1))
        sid += 1
        i = end + 1
    return segs


def _line_to_segment(segs: List[Segment], line_no: int) -> Optional[Segment]:
    for s in segs:
        if s.start_line <= line_no <= s.end_line:
            return s
    return None


def changed_segments(old: str, new: str) -> dict:
    """Map a unified diff (old -> new) onto the segments of `new`."""
    new_segs = segment(new)
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    touched_ids = set()
    changed_new_lines: List[int] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # j1..j2 are 0-based new-line indices (replace/insert); for delete, j1==j2
        rng = range(j1, j2) if j2 > j1 else [j1]
        for j in rng:
            ln = j + 1
            changed_new_lines.append(ln)
            seg = _line_to_segment(new_segs, ln)
            if seg:
                touched_ids.add(seg.id)
    touched = [s.to_dict() for s in new_segs if s.id in touched_ids]
    return {
        "segments_total": len(new_segs),
        "segments_changed": len(touched),
        "changed": touched,
        "changed_lines": sorted(set(changed_new_lines)),
        "note": "Only these segments need regeneration; the rest are preserved.",
    }
