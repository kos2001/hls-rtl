"""RTL schematic extraction (yosys netlist -> layered graph).

Commercial flows give you a schematic view next to the source (Verdi's schematic,
Innovus' netlist browser) because "which cell drives this net" is far faster to see
than to read. `yosys show` would do it, but it shells out to graphviz `dot`, which
is not part of this project's toolchain. So: emit the netlist as JSON, build the
graph here, and let the browser draw it. No extra system dependency.

The netlist is taken *after* `proc` but *before* `techmap`, i.e. RTL-level cells
($mux, $add, $adff, $memrd...) rather than gates. That is the level an RTL engineer
reviews at; a gate netlist of the same design is thousands of nodes and unreadable.

Layering: longest-path from the input boundary. Sequential cells are cut points —
their outputs start a new path — which is what turns the design's feedback loops
(FIFO pointers, occupancy counter) into a finite left-to-right drawing instead of
an unresolvable cycle.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

_ROOT = Path(__file__).resolve().parents[1]
_RTL = _ROOT / "rtl" / "gamma.v"

# Cells whose outputs do not combinationally depend on their inputs. Cutting the
# graph here is what makes a cyclic sequential design drawable.
SEQ_TYPES = {"$dff", "$dffe", "$adff", "$adffe", "$sdff", "$sdffe",
             "$dlatch", "$adlatch", "$ff", "$memwr", "$memwr_v2"}

# Display names — "$mux" means nothing on a canvas; "MUX" does.
TYPE_LABEL = {
    "$mux": "MUX", "$pmux": "PMUX", "$eq": "==", "$ne": "!=", "$lt": "<",
    "$le": "<=", "$gt": ">", "$ge": ">=", "$add": "+", "$sub": "-",
    "$mul": "*", "$and": "&", "$or": "|", "$xor": "^", "$not": "~",
    "$logic_not": "!", "$logic_and": "&&", "$logic_or": "||",
    "$reduce_bool": "|bool", "$reduce_or": "|or", "$reduce_and": "|and",
    "$adff": "DFF/arst", "$adffe": "DFFE/arst", "$dff": "DFF", "$dffe": "DFFE",
    "$memrd": "MEM rd", "$memrd_v2": "MEM rd", "$memwr": "MEM wr",
    "$memwr_v2": "MEM wr", "$mem_v2": "MEM", "$mem": "MEM",
    "$shiftx": "SHIFT", "$shl": "<<", "$shr": ">>", "$pos": "buf",
}

# Coarse classes drive node colour in the UI.
def _cell_class(cell_type: str) -> str:
    if cell_type in SEQ_TYPES:
        return "seq"
    if cell_type.startswith("$mem"):
        return "mem"
    if cell_type in ("$mux", "$pmux"):
        return "mux"
    if cell_type in ("$eq", "$ne", "$lt", "$le", "$gt", "$ge",
                     "$logic_not", "$logic_and", "$logic_or",
                     "$reduce_bool", "$reduce_or", "$reduce_and"):
        return "logic"
    if cell_type in ("$add", "$sub", "$mul", "$div", "$mod"):
        return "arith"
    return "comb"


# yosys autogenerates cell names as `$<type>$<file>:<line>$<serial>`, and for
# memory cells `$memrd$\\<mem>$<file>:<line>$<serial>`. Both embed an absolute
# temp path, so parse out the parts an engineer can use: the memory/signal name
# and the source line, which lets the UI cross-probe schematic -> RTL.
# `procmux$196`, `procdff$170`, `procmux$104_CMP0` — yosys pass name + serial,
# optionally with a generated suffix. Identifies nothing lookup-able.
_PASS_SERIAL_RE = re.compile(r"^[a-z_]+\$\d+(_[A-Z0-9]+)?$")
_AUTONAME_RE = re.compile(r"^\$[^$]+\$(?:\\(?P<obj>[^$]+)\$)?(?P<file>[^$]*?):(?P<line>\d+)\$\d+$")


def _cell_display(cname: str, ctype: str, params: dict) -> tuple[str, Optional[int]]:
    """(short name, source line) for a cell. Falls back to the raw name for
    user-named instances, which yosys leaves alone."""
    m = _AUTONAME_RE.match(cname)
    if m:
        obj = m.group("obj")
        return (obj or TYPE_LABEL.get(ctype, ctype.lstrip("$"))), int(m.group("line"))
    # `$auto$<pass>.cc:<line>:<pass>$<serial>` — named after the yosys pass that
    # created the cell, not the design. Memory cells still know their array via
    # the MEMID parameter, which is the name worth showing.
    memid = params.get("MEMID")
    if isinstance(memid, str) and memid.strip("\\ "):
        return memid.strip("\\ ")[:40], None
    if "auto$" in cname:
        return TYPE_LABEL.get(ctype, ctype.lstrip("$")), None
    bare = cname.lstrip("\\$")
    # `procmux$196`, `procdff$170` — the yosys pass plus a serial. It identifies
    # nothing an engineer can look up, and repeated under every MUX it is pure
    # noise, so fall back to the type label and let the node show only that.
    if _PASS_SERIAL_RE.match(bare):
        return TYPE_LABEL.get(ctype, ctype.lstrip("$")), None
    return bare[:40], None


def available() -> bool:
    return shutil.which("yosys") is not None


def _run_yosys(verilog: str, top: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / f"{top}.v"
        src.write_text(verilog)
        out = Path(td) / "net.json"
        script = (f"read_verilog {src}; hierarchy -top {top}; proc; "
                  f"opt_clean; write_json {out}")
        proc = subprocess.run(["yosys", "-q", "-p", script],
                              capture_output=True, text=True, timeout=120)
        if not out.exists():
            raise RuntimeError(
                f"yosys produced no netlist (exit {proc.returncode}): "
                f"{(proc.stderr or proc.stdout)[-600:]}"
            )
        return json.loads(out.read_text())


def _bit_key(b) -> Optional[str]:
    """Net identity for one bit. Ints are real nets; '0'/'1'/'x'/'z' are constants
    and must NOT be treated as a shared net (every constant-0 would merge)."""
    return f"n{b}" if isinstance(b, int) else None


def build(verilog: Optional[str] = None, top: str = "gamma",
          max_nodes: int = 400) -> dict:
    """Layered node/edge graph of the RTL netlist, ready to draw."""
    if not available():
        return {"available": False, "error": "yosys not found on PATH"}
    code = verilog if verilog is not None else _RTL.read_text()
    try:
        doc = _run_yosys(code, top)
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as exc:
        return {"available": False, "error": str(exc)}

    mods = doc.get("modules", {})
    mod = mods.get(top) or (next(iter(mods.values())) if mods else None)
    if mod is None:
        return {"available": False, "error": f"module {top} not found in netlist"}

    nodes: List[dict] = []
    drivers: Dict[str, str] = {}          # net bit -> node id driving it
    sinks: Dict[str, List[str]] = defaultdict(list)
    width_of: Dict[str, int] = {}         # net bit -> declared width of its bus
    net_label: Dict[str, str] = {}

    # Readable net names, so an edge can be labelled `fifo_count` not `n42`.
    for name, net in mod.get("netnames", {}).items():
        bits = net.get("bits", [])
        for b in bits:
            k = _bit_key(b)
            if k and k not in net_label:
                net_label[k] = name
                width_of[k] = len(bits)

    # --- boundary ports ---
    for pname, port in mod.get("ports", {}).items():
        direction = port.get("direction", "input")
        nid = f"port:{pname}"
        bits = port.get("bits", [])
        nodes.append({
            "id": nid, "label": pname, "kind": "port",
            "cls": "in" if direction == "input" else "out",
            "direction": direction, "width": len(bits), "type": direction,
        })
        for b in bits:
            k = _bit_key(b)
            if not k:
                continue
            if direction == "input":
                drivers[k] = nid
            else:
                sinks[k].append(nid)

    # --- cells ---
    cells = mod.get("cells", {})
    for cname, cell in cells.items():
        ctype = cell.get("type", "?")
        nid = f"cell:{cname}"
        dirs = cell.get("port_directions", {})
        short, srcline = _cell_display(cname, ctype, cell.get("parameters", {}))
        nodes.append({
            "id": nid,
            "label": TYPE_LABEL.get(ctype, ctype.lstrip("$")),
            "kind": "cell",
            "cls": _cell_class(ctype),
            "type": ctype,
            "name": short,
            "src_line": srcline,
            "seq": ctype in SEQ_TYPES,
            "width": max((len(v) for v in cell.get("connections", {}).values()),
                         default=1),
        })
        for port, bits in cell.get("connections", {}).items():
            d = dirs.get(port, "input")
            for b in bits:
                k = _bit_key(b)
                if not k:
                    continue
                if d in ("output", "inout"):
                    drivers.setdefault(k, nid)
                if d in ("input", "inout"):
                    sinks[k].append(nid)

    # --- edges: one per (driver, sink) pair, merging bits of the same bus ---
    seen: Set[tuple] = set()
    edges: List[dict] = []
    for k, dst_list in sinks.items():
        src = drivers.get(k)
        if src is None:
            continue
        for dst in dst_list:
            if src == dst or (src, dst) in seen:
                continue
            seen.add((src, dst))
            edges.append({
                "from": src, "to": dst,
                "net": net_label.get(k, k),
                "width": width_of.get(k, 1),
            })

    by_id = {n["id"]: n for n in nodes}
    _assign_layers(by_id, edges)

    truncated = len(nodes) > max_nodes
    if truncated:
        keep = {n["id"] for n in sorted(nodes, key=lambda n: n["layer"])[:max_nodes]}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]

    layers = max((n["layer"] for n in nodes), default=0) + 1
    return {
        "available": True,
        "top": top,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "layers": layers,
        "truncated": truncated,
        "stats": _stats(cells),
        "nodes": nodes,
        "edges": edges,
        "note": "RTL-level netlist (yosys proc + opt_clean). Sequential cells cut "
                "the graph, so feedback paths read left-to-right.",
    }


def _assign_layers(by_id: Dict[str, dict], edges: List[dict]) -> None:
    """Longest-path layering with sequential cells and inputs as sources.

    Iterative relaxation rather than a topological sort: the combinational graph
    is acyclic once sequential cells are cut, but `opt_clean` output is not
    guaranteed to be, so a bounded relaxation degrades gracefully where a true
    topo-sort would raise.
    """
    outgoing: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        outgoing[e["from"]].append(e["to"])

    for n in by_id.values():
        n["layer"] = 0

    def is_source(n: dict) -> bool:
        return (n["kind"] == "port" and n["direction"] == "input") or n.get("seq")

    for _ in range(len(by_id) + 1):
        changed = False
        for nid, node in by_id.items():
            base = node["layer"]
            for dst_id in outgoing.get(nid, ()):
                dst = by_id.get(dst_id)
                if dst is None or is_source(dst):
                    continue
                if dst["layer"] < base + 1:
                    dst["layer"] = base + 1
                    changed = True
        if not changed:
            break

    # Outputs always sit on the right-hand rail.
    depth = max((n["layer"] for n in by_id.values()), default=0)
    for n in by_id.values():
        if n["kind"] == "port" and n["direction"] == "output":
            n["layer"] = depth + 1


def _stats(cells: dict) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for c in cells.values():
        out[TYPE_LABEL.get(c.get("type", "?"), c.get("type", "?"))] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
