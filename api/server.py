"""FastAPI api-server for the gamma verification dashboard.

Endpoints:
  GET  /health        -> liveness + gateway-key + verilator availability
  GET  /verification  -> the 3-way scoreboard results (live from the golden model)
  POST /chat          -> RTL-assistant chat, proxied to the Hermes Gateway

The SPA calls these under `/api/*`; the prefix is stripped in-process so the
same build works behind a dev proxy and when FastAPI serves the built frontend.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_settings
from .hermes_engine import HermesGateway, close_shared_client
from . import rtl_qor, signoff as signoff_mod, progressive as progressive_mod
from .telemetry import archive

_ROOT = Path(__file__).resolve().parents[1]
# The results generator lives in scripts/ and wires up golden/ + tb/ on import.
sys.path.insert(0, str(_ROOT / "scripts"))
from gen_dashboard_data import build_results  # noqa: E402

# Imported after the path setup above (oracle pulls in the golden model).
from . import oracle as oracle_mod  # noqa: E402
from . import rtl_segments, reflection, equiv as equiv_mod, agents  # noqa: E402
from . import graph_rag  # noqa: E402

app = FastAPI(title="Gamma Verification API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _strip_api_prefix(request, call_next):
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


@app.on_event("shutdown")
def _on_shutdown() -> None:
    close_shared_client()


# ---- Schemas ----
class HealthOut(BaseModel):
    ok: bool
    model: str
    has_key: bool
    verilator: bool
    gateway_base_url: str


class ChatIn(BaseModel):
    message: str
    user_id: str = "default-user"


class ChatOut(BaseModel):
    content: str
    user_id: str


_RTL_ASSISTANT_INSTRUCTIONS = (
    "You are an RTL verification assistant for the 'gamma' DUT: a 1 pixel/cycle, "
    "ready/valid, per-channel-LUT gamma-correction core verified by a 3-way "
    "(Python golden / SystemC / Verilog RTL) bit-exact scoreboard. Answer "
    "concisely and technically about the design, its handshake/latency contract, "
    "the test set, and verification results."
)


# ---- Routes ----
@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    s = load_settings()
    return HealthOut(
        ok=True,
        model=s.model_label,
        has_key=s.has_real_key,
        verilator=shutil.which("verilator") is not None,
        gateway_base_url=s.hermes_gateway_base_url,
    )


@app.get("/verification")
def verification() -> Dict[str, Any]:
    """Live 3-way scoreboard results, computed from the golden model over the
    canonical test set. SHA-256 frame hashes match the cocotb regression."""
    results = build_results()
    archive.record("verification", {
        "status": "pass" if results["summary"]["failed"] == 0 else "fail",
        "score": round(100 * results["summary"]["passed"]
                       / max(1, results["summary"]["total_patterns"])),
        "passed": results["summary"]["passed"],
        "total": results["summary"]["total_patterns"],
    })
    return results


# ---- RTL quality / sign-off (ported from ai_driven_rtl) ----
class CodeIn(BaseModel):
    code: Optional[str] = None  # defaults to the project RTL (rtl/gamma.v)


@app.get("/analyze")
def analyze_get() -> Dict[str, Any]:
    """Deterministic QoR report (0-100 score + grade) for the project RTL."""
    return rtl_qor.analyze().to_dict()


@app.post("/analyze")
def analyze_post(req: CodeIn) -> Dict[str, Any]:
    return rtl_qor.analyze(req.code).to_dict()


@app.get("/drc")
def drc_get() -> Dict[str, Any]:
    """Coded, severity-graded RTL design-rule report for the project RTL."""
    return rtl_qor.run_drc()


@app.post("/drc")
def drc_post(req: CodeIn) -> Dict[str, Any]:
    return rtl_qor.run_drc(req.code)


@app.get("/lint")
def lint_get() -> Dict[str, Any]:
    r = rtl_qor.lint(rtl_qor.project_rtl())
    return {"ok": r.ok, "available": r.available, "top": r.top, "issues": r.issues}


class SignoffIn(BaseModel):
    run_regression: bool = True


@app.post("/signoff")
def signoff_route(req: SignoffIn) -> Dict[str, Any]:
    """Run the full sign-off ladder (lint -> design -> synth -> cocotb
    regression) on the project RTL and return a consolidated verdict. The
    simulate stage runs the real 3-way scoreboard, so it can take a few seconds."""
    return signoff_mod.run_signoff(run_regression=req.run_regression)


@app.get("/telemetry/{kind}")
def telemetry(kind: str) -> Dict[str, Any]:
    """Aggregated run history for a kind ('signoff' | 'verification')."""
    return archive.summary(kind)


# ---- #1 progressive-coding oracle ----
class ProgressiveIn(BaseModel):
    run_regression: bool = True


@app.post("/progressive")
def progressive_route(req: ProgressiveIn) -> Dict[str, Any]:
    """Representation x pattern equivalence matrix (golden / systemc / rtl),
    framing the NL->C++->RTL progressive-coding flow with the 3-way scoreboard
    as ground-truth oracle. Runs the real cocotb regression (a few seconds)."""
    return progressive_mod.run_progressive(run_regression=req.run_regression)


# ---- #2 golden-as-oracle ----
class OracleCheckIn(BaseModel):
    pattern: str
    output: List[List[int]]


@app.get("/oracle")
def oracle_contract() -> Dict[str, Any]:
    """Verification contract auto-derived from the Python golden — the hashes
    any SystemC/RTL/LLM candidate must reproduce bit-exactly."""
    return oracle_mod.gamma_oracle().contract()


@app.post("/oracle/check")
def oracle_check(req: OracleCheckIn) -> Dict[str, Any]:
    """Check a candidate output frame for one pattern against the golden oracle."""
    return oracle_mod.gamma_oracle().check(req.pattern, req.output)


# ---- #3 RTL segment traceability ----
class SegDiffIn(BaseModel):
    new: str
    old: Optional[str] = None  # defaults to the project RTL


@app.get("/segments")
def segments_get() -> Dict[str, Any]:
    segs = rtl_segments.segment(rtl_qor.project_rtl())
    return {"count": len(segs), "segments": [s.to_dict() for s in segs]}


@app.post("/segments/diff")
def segments_diff(req: SegDiffIn) -> Dict[str, Any]:
    old = req.old if req.old is not None else rtl_qor.project_rtl()
    return rtl_segments.changed_segments(old, req.new)


# ---- #4 planner agent (LLM; 503 without gateway key) ----
class PlanIn(BaseModel):
    uarch: str
    algorithm: str = ""
    user_id: str = "default-user"


@app.post("/plan")
async def plan_route(req: PlanIn) -> Dict[str, Any]:
    s = load_settings()
    if not s.has_real_key:
        raise HTTPException(503, "Hermes Gateway credentials missing (set HERMES_GATEWAY_API_KEY)")
    prompt = f"uArch document (existing + changed):\n{req.uarch}\n\nAlgorithm (Python):\n{req.algorithm}"
    try:
        resp = await agents.build_planner().run_async(prompt, user_id=req.user_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return {"plan": resp.content}


# ---- #5 adaptive reflection (deterministic; LLM-free) ----
class ReflectIn(BaseModel):
    stages: Optional[Dict[str, str]] = None


@app.post("/reflect")
def reflect_route(req: ReflectIn) -> Dict[str, Any]:
    """Trace a failure to its root pipeline stage. With explicit `stages` it
    classifies those; otherwise it derives a fast (no-regression) snapshot from
    the static analyzer."""
    if req.stages:
        return reflection.classify(req.stages)
    rep = rtl_qor.analyze()
    lp = rep.metrics.get("lint_pass")
    sy = rep.metrics.get("synthesizable")
    design_fail = any(c.severity == "error" and not c.ok
                      and c.id not in ("synthesizable", "lint_clean") for c in rep.checks)
    stages = {
        "lint": "skip" if lp is None else ("pass" if lp else "fail"),
        "design": "fail" if design_fail else "pass",
        "synthesize": "skip" if sy is None else ("pass" if sy else "fail"),
    }
    return reflection.classify(stages)


# ---- #7 equivalence (LEC) ----
class EquivIn(BaseModel):
    new: Optional[str] = None  # defaults to the project RTL (self-equivalence)
    old: Optional[str] = None  # defaults to the project RTL
    pixel_w: int = 2
    lut_depth: int = 4


@app.post("/equiv")
def equiv_route(req: EquivIn) -> Dict[str, Any]:
    """Prove the new RTL is logically equivalent to the old (yosys sequential
    LEC, reduced params for tractability). Omit `new` to self-equiv the project
    RTL as a sanity check."""
    project = rtl_qor.project_rtl()
    old = req.old if req.old is not None else project
    new = req.new if req.new is not None else project
    return equiv_mod.check_equivalence(old, new, pixel_w=req.pixel_w,
                                       lut_depth=req.lut_depth).to_dict()


# ---- #6 Graph RAG (graphify) ----
@app.get("/graph/explain")
def graph_explain(node: str, budget: int = 1500) -> Dict[str, Any]:
    """Knowledge-graph neighborhood of a node (function/file/module) — grounding
    context for generation/incremental."""
    return graph_rag.explain(node, budget=budget)


@app.get("/graph/query")
def graph_query(q: str, budget: int = 2000, dfs: bool = False) -> Dict[str, Any]:
    """Traverse the repo knowledge graph for a concept/relationship."""
    return graph_rag.query(q, budget=budget, dfs=dfs)


@app.post("/chat", response_model=ChatOut)
async def chat(req: ChatIn) -> ChatOut:
    s = load_settings()
    if not s.has_real_key:
        raise HTTPException(
            503, "Hermes Gateway credentials missing (set HERMES_GATEWAY_API_KEY)"
        )
    gw = HermesGateway(
        base_url=s.hermes_gateway_base_url,
        api_key=s.hermes_gateway_api_key,
        model=s.hermes_gateway_model,
        instructions=agents.apply_eda_skills(_RTL_ASSISTANT_INSTRUCTIONS),
        timeout=s.hermes_gateway_timeout,
    )
    try:
        resp = await gw.run_async(req.message, user_id=req.user_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return ChatOut(content=resp.content, user_id=req.user_id)


# Serve the built SPA when present (production single-container mode).
_FRONTEND_DIST = _ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
