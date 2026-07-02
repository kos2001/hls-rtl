"""Adaptive reflection — deterministic error-source tracer (improvement #5).

The gateway-free core of Spec2RTL-Agent's reflection enabler: given the sign-off
stage signals, classify which stage is the root cause and what to do next. This
runs with no LLM, so it is testable and always available; api/agents.py adds an
optional natural-language explanation on top.

Stage ordering encodes the dependency: a failure at an earlier stage is the root
cause and later failures are likely downstream symptoms.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Earliest-first: the first failing stage is the root cause.
_ORDER = ["lint", "design", "synthesize", "simulate", "formal"]

_DIAGNOSIS = {
    "lint": ("rtl-syntax",
             "Verilator lint failed — a syntactic / elaboration error in the RTL.",
             "Fix the lint errors first; they block every downstream stage."),
    "design": ("rtl-structure",
               "A structural design-rule check failed (reset / blocking-assignment / latch / CDC).",
               "Correct the flagged segment; re-run analyze/drc to confirm."),
    "synthesize": ("rtl-synthesizability",
                   "yosys could not synthesize the RTL (unsynthesizable construct or inferred latch).",
                   "Remove the unsynthesizable construct; drive every output on every path."),
    "simulate": ("functional",
                 "The 3-way scoreboard mismatched: RTL/SystemC output differs from the Python golden.",
                 "The behavior is wrong, not the syntax — revisit the datapath/LUT logic "
                 "(or the C++ intermediate) against the golden; the testbench itself is golden-derived."),
    "formal": ("assertion-or-spec",
               "A formal property was violated (counterexample found).",
               "Review the counterexample: fix the RTL or the assertion; model reset for sequential props."),
}


def classify(stages: Dict[str, str]) -> dict:
    """stages: {stage_name: 'pass'|'fail'|'skip'}. Returns the root-cause stage."""
    failures = [s for s in _ORDER if stages.get(s) == "fail"]
    if not failures:
        skipped = [s for s in _ORDER if stages.get(s) == "skip"]
        return {
            "ok": True,
            "root_stage": None,
            "diagnosis": "no failing stage",
            "skipped": skipped,
            "action": ("Install the missing tool(s) to make the verdict unconditional."
                       if skipped else "All applicable gating stages pass."),
        }
    root = failures[0]
    source, diagnosis, action = _DIAGNOSIS[root]
    downstream = [s for s in failures[1:]]
    return {
        "ok": False,
        "root_stage": root,
        "error_source": source,
        "diagnosis": diagnosis,
        "action": action,
        "downstream_symptoms": downstream,
        "note": "Earliest failing stage is the root cause; later failures are "
                "likely downstream symptoms — fix the root first.",
    }


def reflect_on_signoff(report: dict) -> dict:
    """Convenience: pull stage statuses out of a sign-off report and classify."""
    stages = {s["name"]: s["status"] for s in report.get("stages", [])}
    out = classify(stages)
    out["verdict"] = report.get("verdict")
    return out
