"""Graph RAG over the repo (improvement #6).

uArch / RTL structure is inherently a graph (module connectivity, signal flow,
clock domains, who-calls-what). Vector RAG misses those relations. `graphify`
builds a persistent knowledge graph (graphify-out/graph.json) with sub-second
BFS/DFS traversal; this module exposes it as grounding context the pipeline can
attach to a generation / incremental request ("this signal belongs to which
module / is read by what").

Pure traversal — no LLM key required (graphify does the semantic match over the
prebuilt graph). Returns 503-style 'unavailable' when the graph isn't built.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
_GRAPH = _ROOT / "graphify-out" / "graph.json"
_TIMEOUT = 60


def available() -> bool:
    return shutil.which("graphify") is not None and _GRAPH.exists()


def _run(args: list, budget: int) -> dict:
    if not available():
        return {"available": False,
                "error": "graphify or graphify-out/graph.json missing; build with `graphify update . --force`"}
    try:
        proc = subprocess.run(["graphify", *args, "--budget", str(budget)],
                              cwd=str(_ROOT), capture_output=True, text=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "graphify timed out"}
    out = "\n".join(l for l in (proc.stdout + proc.stderr).splitlines()
                    if "warning: skill" not in l)
    return {"available": True, "result": out.strip()}


def explain(node: str, budget: int = 1500) -> dict:
    return _run(["explain", node], budget)


def query(q: str, budget: int = 2000, dfs: bool = False) -> dict:
    args = ["query", q] + (["--dfs"] if dfs else [])
    return _run(args, budget)
