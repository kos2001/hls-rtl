"""VCD waveform extraction for the workbench wave viewer.

Commercial flows (Verdi, SimVision) put a waveform next to every failing test —
the scoreboard says *that* the DUT disagreed, the waveform says *when* and under
what handshake conditions. This module turns `tb/dump.vcd` into a compact JSON
the browser can draw without shipping a 3 MB file to it.

The cocotb/Verilator run emits `dump.vcd` in tb/ when built with `WAVES=1`
(EXTRA_ARGS += --trace). Because tracing costs ~30% sim time it is opt-in here
too: `ensure_dump()` reuses an existing dump unless asked to regenerate.

Design notes:
  * Streaming parse — the file is read line-by-line, never fully materialised.
  * Only the requested scope's signals are tracked; ids outside it are dropped
    during the scan, which is what keeps a 330k-line dump cheap.
  * A window is a time range plus a transition budget. Exceeding the budget
    truncates and says so rather than silently dropping edges.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
_TB = _ROOT / "tb"
_DUMP = _TB / "dump.vcd"

# "$var wire 8 & in_r [7:0] $end"  ->  kind, width, id, name
_VAR_RE = re.compile(r"\$var\s+(\w+)\s+(\d+)\s+(\S+)\s+([^\s$]+)(?:\s+\[[^\]]*\])?\s*\$end")
_SCOPE_RE = re.compile(r"\$scope\s+\w+\s+(\S+)\s+\$end")
_TIMESCALE_RE = re.compile(r"\$timescale\s+(\d+)\s*(\w+)\s*\$end")

_TS_UNITS = {"s": 1e0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}

# Verilator traces elaboration parameters as ordinary $vars, so a naive viewer
# draws LUT_DEPTH as a 32-bit "signal" that never changes. This RTL follows the
# usual Verilog convention — parameters ALL_CAPS, signals lower_snake — so the
# name tells them apart, and a constant value across the window confirms it.
_PARAM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Signals a reviewer wants first for a ready/valid pixel core, in draw order.
PREFERRED_ORDER = (
    "clk", "rst_n",
    "in_valid", "in_ready", "in_r", "in_g", "in_b",
    "out_valid", "out_ready", "out_r", "out_g", "out_b",
    "lut_we", "lut_ch", "lut_addr", "lut_wdata",
)


@dataclass
class Signal:
    name: str
    width: int
    kind: str
    scope: str
    transitions: List[Tuple[int, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "kind": self.kind,
            "scope": self.scope,
            # [[time, value], ...] — value is "0"/"1"/"x"/"z" or a bit string
            "transitions": [[t, v] for t, v in self.transitions],
        }


def dump_path() -> Path:
    return _DUMP


def dump_status() -> dict:
    """Whether a waveform exists, without parsing it."""
    if not _DUMP.exists():
        return {"available": False, "path": str(_DUMP)}
    st = _DUMP.stat()
    return {
        "available": True,
        "path": str(_DUMP),
        "size_bytes": st.st_size,
        "modified": int(st.st_mtime),
    }


def ensure_dump(*, regenerate: bool = False, timeout: int = 600,
                bp_profile: str = "single") -> dict:
    """Make sure a VCD exists, running the traced regression if needed.

    `BP_PROFILE=single` keeps the traced run short — one backpressure profile is
    enough to *look at* the handshake; the full cross-product is the regression's
    job, not the viewer's.
    """
    if _DUMP.exists() and not regenerate:
        return {"ran": False, **dump_status()}
    env = {**os.environ, "WAVES": "1", "BP_PROFILE": bp_profile}
    try:
        proc = subprocess.run(
            ["make", "-s", "WAVES=1"], cwd=str(_TB), env=env,
            capture_output=True, text=True, timeout=timeout,
        )
        log = (proc.stdout + proc.stderr)[-4000:]
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        return {"ran": True, "ok": False, "error": f"regression timed out after {timeout}s",
                **dump_status()}
    except OSError as exc:
        return {"ran": True, "ok": False, "error": str(exc), **dump_status()}
    return {"ran": True, "ok": ok, "log_tail": log, **dump_status()}


def _pick_scope(scopes: Dict[str, int], requested: Optional[str]) -> Optional[str]:
    if requested and requested in scopes:
        return requested
    # Verilator emits a flat `$rootio` scope with the DUT ports — the most useful
    # default. Otherwise take the scope carrying the most signals.
    if "gamma" in scopes:
        return "gamma"
    if "$rootio" in scopes:
        return "$rootio"
    return max(scopes, key=lambda s: scopes[s]) if scopes else None


def _parse_header(fh) -> Tuple[Dict[str, Signal], float, Dict[str, int], Dict[str, List[str]]]:
    """Read up to $enddefinitions. Returns id->Signal, timescale seconds,
    scope->signal count, and scope->signal names."""
    ids: Dict[str, Signal] = {}
    scope_stack: List[str] = []
    counts: Dict[str, int] = {}
    names: Dict[str, List[str]] = {}
    ts_seconds = 1e-12
    for line in fh:
        s = line.strip()
        if s.startswith("$timescale"):
            m = _TIMESCALE_RE.search(s)
            if m:
                ts_seconds = int(m.group(1)) * _TS_UNITS.get(m.group(2), 1e-12)
        elif s.startswith("$scope"):
            m = _SCOPE_RE.search(s)
            scope_stack.append(m.group(1) if m else "?")
        elif s.startswith("$upscope"):
            if scope_stack:
                scope_stack.pop()
        elif s.startswith("$var"):
            m = _VAR_RE.search(s)
            if not m:
                continue
            kind, width, vid, name = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            scope = scope_stack[-1] if scope_stack else "(top)"
            counts[scope] = counts.get(scope, 0) + 1
            names.setdefault(scope, []).append(name)
            # One VCD id can alias several names (e.g. equal-valued parameters).
            # Keep the first — the viewer shows one row per id.
            ids.setdefault(vid, Signal(name=name, width=width, kind=kind, scope=scope))
        elif s.startswith("$enddefinitions"):
            break
    return ids, ts_seconds, counts, names


def _order_key(sig: Signal) -> Tuple[int, str]:
    try:
        return (PREFERRED_ORDER.index(sig.name), "")
    except ValueError:
        return (len(PREFERRED_ORDER), sig.name)


def _is_parameter(sig: Signal) -> bool:
    """An elaboration constant, not waveform traffic: ALL_CAPS name that never
    changes in the scanned window. Both conditions are required — a genuine
    signal that happens to be quiet here must stay on the canvas."""
    return bool(_PARAM_NAME_RE.match(sig.name)) and len(sig.transitions) <= 1


def extract(*, scope: Optional[str] = None, signals: Optional[List[str]] = None,
            start: int = 0, end: Optional[int] = None,
            max_transitions: int = 20000,
            split_parameters: bool = True) -> dict:
    """Parse the dump into a drawable waveform window.

    `start`/`end` are in the VCD's own time units (ps for the Verilator dump).
    `max_transitions` is a total budget across all signals; hitting it sets
    `truncated` and reports the last time actually covered, so the UI can say
    "showing 0-N" instead of drawing a misleadingly quiet tail.
    """
    if not _DUMP.exists():
        return {"available": False, "error": "no dump.vcd — run the traced regression first"}

    with _DUMP.open("r", errors="replace") as fh:
        ids, ts_seconds, counts, names = _parse_header(fh)
        chosen = _pick_scope(counts, scope)
        wanted = {vid: sig for vid, sig in ids.items() if sig.scope == chosen}
        if signals:
            keep = set(signals)
            wanted = {vid: sig for vid, sig in wanted.items() if sig.name in keep}
        # Parameters are elaboration constants, not waveform traffic.
        wanted = {vid: sig for vid, sig in wanted.items() if sig.width <= 64}

        t = 0
        total = 0
        truncated = False
        last_t = 0
        for line in fh:
            s = line.strip()
            if not s:
                continue
            c = s[0]
            if c == "#":
                try:
                    t = int(s[1:])
                except ValueError:
                    continue
                if end is not None and t > end:
                    break
                last_t = t
                continue
            if t < start:
                # still fast-forwarding; keep the latest value so the window
                # starts from a correct level rather than an undefined one
                pass
            if c in "01xXzZ":
                vid, val = s[1:], c.lower()
            elif c in "bB":
                val, _, vid = s[1:].partition(" ")
                val = val.strip().lower()
                vid = vid.strip()
            elif c in "rR":
                val, _, vid = s[1:].partition(" ")
                val, vid = val.strip(), vid.strip()
            else:
                continue  # $dumpvars / $end / directives
            sig = wanted.get(vid)
            if sig is None:
                continue
            if sig.transitions and sig.transitions[-1][1] == val:
                continue  # VCD may restate a value; don't draw a non-edge
            if t < start:
                # collapse pre-window history into a single starting level
                if sig.transitions:
                    sig.transitions[-1] = (start, val)
                else:
                    sig.transitions.append((start, val))
                continue
            sig.transitions.append((t, val))
            total += 1
            if total >= max_transitions:
                truncated = True
                break

    collected = list(wanted.values())
    params: List[Signal] = []
    if split_parameters:
        params = [s for s in collected if _is_parameter(s)]
        collected = [s for s in collected if not _is_parameter(s)]
    ordered = sorted(collected, key=_order_key)
    return {
        "available": True,
        # Shown as a static list beside the waveform, the way a tool lists
        # elaboration parameters rather than plotting them.
        "parameters": [
            {"name": s.name, "width": s.width,
             "value": s.transitions[0][1] if s.transitions else "-"}
            for s in sorted(params, key=lambda s: s.name)
        ],
        "scope": chosen,
        "scopes": [{"name": k, "signals": v} for k, v in sorted(counts.items())],
        "signal_names": names.get(chosen, []),
        "timescale_seconds": ts_seconds,
        "time_unit": _unit_label(ts_seconds),
        "start": start,
        "end": last_t,
        "truncated": truncated,
        "transition_count": total,
        "signals": [s.to_dict() for s in ordered],
    }


def _unit_label(seconds: float) -> str:
    for label, mult in (("s", 1e0), ("ms", 1e-3), ("us", 1e-6),
                        ("ns", 1e-9), ("ps", 1e-12), ("fs", 1e-15)):
        if abs(seconds - mult) < mult * 0.01:
            return label
    return "ps"
