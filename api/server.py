"""FastAPI api-server for the gamma verification dashboard.

Endpoints:
  GET  /health        -> liveness + gateway-key + verilator availability
  GET  /verification  -> the 3-way scoreboard results (live from the golden model)
  POST /chat          -> RTL-assistant chat, proxied to the Hermes Gateway

The SPA calls these under `/api/*`; the prefix is stripped in-process so the
same build works behind a dev proxy and when FastAPI serves the built frontend.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
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
from . import skills as skills_mod, waveform as waveform_mod, schematic as schematic_mod  # noqa: E402
from . import knowledge as kb, improve as improve_mod, mutate as mutate_mod  # noqa: E402
from . import coverage as coverage_mod  # noqa: E402
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
    # Per-conversation id from the UI: same id -> transcript continuity on the
    # gateway; a new id (UI "Clear") starts fresh. None -> stateless call.
    session: Optional[str] = None


class ChatOut(BaseModel):
    content: str
    user_id: str
    # Which knowledge-base passages were injected as grounding for this answer.
    # Surfaced so a reader can check the answer against its sources instead of
    # taking the agent's word for it.
    citations: List[Dict[str, Any]] = []


_RTL_ASSISTANT_INSTRUCTIONS = (
    "You are an RTL verification assistant for the 'gamma' DUT: a 1 pixel/cycle, "
    "ready/valid, per-channel-LUT gamma-correction core verified by a 3-way "
    "(Python golden / SystemC / Verilog RTL) bit-exact scoreboard. Answer "
    "concisely and technically about the design, its handshake/latency contract, "
    "the test set, and verification results. Answer in the same language the "
    "user writes in (Korean question -> Korean answer). "
    "Ground every factual claim about this design in the DESIGN KNOWLEDGE BASE "
    "passages below and cite the [path:lines] label you relied on. If the "
    "knowledge base does not cover something, say so plainly instead of "
    "inferring it — a missing passage is not permission to guess."
)


def _design_digest(query: str = "", max_chars: int = 9000):
    """Grounding context for one request, retrieved for THIS question.

    This used to be a fixed 1800-char digest — the same parameters and pass
    count for every question. That grounds "what is in_ready" and nothing else;
    anything about backpressure, the SystemC mirror, or why a pattern exists fell
    back on session memory. `api/knowledge.py` now retrieves the passages that
    match the question, on top of pinned chunks (module contract, current
    pass/fail) that are context for everything.

    Returns (context_block, citations).
    """
    return kb.context_for(query, budget=max_chars)


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
    planner = agents.build_planner()
    # Retrieve against the CHANGED delta, not the whole uArch. The full spec is
    # already in the prompt as the planner's input; querying with it just
    # retrieves the spec's own sections back — spending the grounding budget on
    # text the model can already see. The delta is what needs surrounding
    # context (which RTL block, which test, which sibling model).
    _, _, delta = req.uarch.partition("## 9. CHANGED")
    query = (delta or req.uarch)[:1200] + "\n" + req.algorithm[:400]
    ctx, citations = _design_digest(query)
    planner.instructions += ctx
    try:
        # Fresh session per plan request: plans are self-contained and must not
        # inherit stale design facts from earlier transcripts.
        resp = await planner.run_async(prompt, user_id=req.user_id,
                                       session_id=uuid.uuid4().hex)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return {"plan": resp.content, "citations": citations}


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


# ---- Self-improvement loop ----
class ProveIn(BaseModel):
    code: Optional[str] = None      # None -> prove the committed rtl/gamma.v
    bp_profile: str = "split"
    run_regression: bool = True


@app.post("/improve/prove")
def improve_prove(req: ProveIn) -> Dict[str, Any]:
    """Gate a candidate against the oracle: lint, design rules, synthesis, then
    the real cocotb regression run against THIS code. No LLM. `PROVEN` means
    bit-exact values and ordering — see `proves` / `does_not_prove`."""
    return improve_mod.prove(req.code, bp_profile=req.bp_profile,
                             run_regression=req.run_regression).to_dict()


@app.get("/improve/mutants")
def improve_mutants(limit: int = 0) -> Dict[str, Any]:
    """The mutant set without running anything — cheap, for seeing which fault
    classes are covered before paying for a campaign."""
    return mutate_mod.preview(limit=limit)


class MutateIn(BaseModel):
    limit: int = 12
    bp_profile: str = "single"
    operators: Optional[List[str]] = None


@app.post("/improve/mutate")
def improve_mutate(req: MutateIn) -> Dict[str, Any]:
    """Inject single faults and run the real gate on each.

    Measures detection power, which a pass rate does not. Roughly 10s per
    mutant, so `limit` is there to keep an interactive run interactive."""
    return mutate_mod.run(limit=req.limit, operators=req.operators,
                          bp_profile=req.bp_profile)


@app.get("/coverage")
def coverage_route(bp_profile: str = "single") -> Dict[str, Any]:
    """Line coverage from an instrumented Verilator run.

    `never-executed` is the signal worth acting on. `partial` frequently
    reflects how Verilator attributes branch points to declaration lines, and
    the elaboration guards in the `translate_off` block are exempt — they fire
    only on an illegal parameterisation, so requiring them would mean the only
    route to 100% is to break the design."""
    return coverage_mod.run(bp_profile=bp_profile)


@app.get("/improve/audit")
def improve_audit() -> Dict[str, Any]:
    """Ranked gaps in EVIDENCE, not known defects. Deterministic, no gateway."""
    return improve_mod.audit()


class LoopIn(BaseModel):
    goal: str
    max_iters: int = 3
    bp_profile: str = "single"
    user_id: str = "default-user"


@app.post("/improve/loop")
async def improve_loop(req: LoopIn) -> Dict[str, Any]:
    """Propose → prove → reflect, bounded, with the oracle as the only judge.
    Returns every attempt including failures. Nothing is written to rtl/."""
    return await improve_mod.run_loop(req.goal, max_iters=req.max_iters,
                                      bp_profile=req.bp_profile,
                                      user_id=req.user_id)


class ApplyIn(BaseModel):
    candidate_path: str


@app.post("/improve/apply")
def improve_apply(req: ApplyIn) -> Dict[str, Any]:
    """Promote a proven candidate to rtl/gamma.v. Re-proves it first and refuses
    if it is not equivalent; backs up the current RTL."""
    try:
        return improve_mod.apply_candidate(req.candidate_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


# ---- Project documents ----
# Whitelisted so the endpoint cannot be turned into an arbitrary file read.
_DOCS = {
    "MANUAL": _ROOT / "docs" / "MANUAL.md",
    "UARCH": _ROOT / "docs" / "UARCH.md",
    "TESTPLAN": _ROOT / "TESTPLAN.md",
    "README": _ROOT / "README.md",
}


@app.get("/doc/{name}")
def doc(name: str, lang: str = "en") -> Dict[str, Any]:
    """A project document by name, for rendering inside the workbench.

    `lang=ko` prefers a `.ko.md` sibling and falls back to the English original
    when none exists — a missing translation should degrade to a readable
    document, never to a 404.
    """
    path = _DOCS.get(name.upper())
    if path is None:
        raise HTTPException(404, f"unknown document {name!r}; have {sorted(_DOCS)}")
    translated = False
    if lang and lang != "en":
        alt = path.with_suffix("").with_suffix(f".{lang}.md") if path.name.endswith(".md") \
            else path
        alt = path.parent / f"{path.name[:-3]}.{lang}.md"
        if alt.exists():
            path, translated = alt, True
    if not path.exists():
        raise HTTPException(404, f"{path.relative_to(_ROOT)} not found")
    text = path.read_text(encoding="utf-8")
    return {"name": name.upper(), "path": str(path.relative_to(_ROOT)),
            "lang": lang if translated else "en", "translated": translated,
            "chars": len(text), "text": text}


# ---- Microarchitecture spec ----
@app.get("/uarch")
def uarch() -> Dict[str, Any]:
    """The uArch specification (docs/UARCH.md) — the design input `POST /plan`
    consumes. Served so the UI can seed the planner with the real document
    instead of a placeholder the user has to retype."""
    p = _ROOT / "docs" / "UARCH.md"
    if not p.exists():
        raise HTTPException(404, "docs/UARCH.md not found")
    text = p.read_text(encoding="utf-8")
    # The "## CHANGED" tail is where a proposal goes; split it out so the UI can
    # show the stable spec read-only and let the user edit only the delta.
    marker = "\n## 9. CHANGED"
    head, _, tail = text.partition(marker)
    return {
        "path": "docs/UARCH.md",
        "chars": len(text),
        "spec": head.rstrip(),
        "changed_section": (marker + tail).strip() if tail else "",
    }


# ---- Knowledge base (retrieval grounding) ----
@app.get("/kb/stats")
def kb_stats() -> Dict[str, Any]:
    """Index size and composition. The index rebuilds automatically when a
    source file's mtime changes, so this also shows how fresh it is."""
    return kb.stats()


@app.get("/kb/search")
def kb_search(q: str, limit: int = 8, text: bool = False) -> Dict[str, Any]:
    """What the agent would be given as grounding for `q` — the same retrieval
    path /chat uses, exposed so the ranking can be inspected directly."""
    hits = kb.search(q, limit=limit)
    return {
        "query": q,
        "count": len(hits),
        "results": [{**r.chunk.to_dict(include_text=text), "score": r.score}
                    for r in hits],
    }


@app.get("/kb/context")
def kb_context(q: str, budget: int = 9000) -> Dict[str, Any]:
    """The exact grounding block injected for `q`, for debugging prompts."""
    block, citations = kb.context_for(q, budget=budget)
    return {"query": q, "chars": len(block), "citations": citations, "context": block}


# ---- Hermes skills (what the agent can actually load) ----
@app.get("/skills")
def skills_route(refresh: bool = False) -> Dict[str, Any]:
    """Which skills the gateway's serving profile really has, vs. what this
    project wants. `source: "repo-only"` means the skill is authored in skills/
    but not yet synced — run scripts/sync_hermes_skills.py."""
    return skills_mod.report(refresh=refresh).to_dict()


# ---- Waveform (Verdi/SimVision-style viewer data) ----
@app.get("/waveform/status")
def waveform_status() -> Dict[str, Any]:
    return waveform_mod.dump_status()


class WaveRunIn(BaseModel):
    regenerate: bool = False
    bp_profile: str = "single"


@app.post("/waveform/run")
def waveform_run(req: WaveRunIn) -> Dict[str, Any]:
    """Ensure a VCD exists, running the traced (WAVES=1) regression if needed.
    Tracing costs ~30% sim time, so an existing dump is reused unless
    `regenerate` is set."""
    return waveform_mod.ensure_dump(regenerate=req.regenerate,
                                    bp_profile=req.bp_profile)


@app.get("/waveform")
def waveform_route(scope: Optional[str] = None, start: int = 0,
                   end: Optional[int] = None,
                   max_transitions: int = 20000) -> Dict[str, Any]:
    """A drawable window of the dump: signals plus their value changes.
    Times are in the dump's own units (ps for the Verilator trace)."""
    return waveform_mod.extract(scope=scope, start=start, end=end,
                                max_transitions=max_transitions)


# ---- Schematic (RTL netlist graph) ----
@app.get("/schematic")
def schematic_route(top: str = "gamma", max_nodes: int = 400) -> Dict[str, Any]:
    """Layered RTL-level netlist graph (yosys proc + opt_clean) for the
    schematic view. Cells carry their source line for cross-probing."""
    return schematic_mod.build(top=top, max_nodes=max_nodes)


@app.post("/schematic")
def schematic_post(req: CodeIn, top: str = "gamma") -> Dict[str, Any]:
    return schematic_mod.build(req.code, top=top)


@app.post("/chat", response_model=ChatOut)
async def chat(req: ChatIn) -> ChatOut:
    s = load_settings()
    if not s.has_real_key:
        raise HTTPException(
            503, "Hermes Gateway credentials missing (set HERMES_GATEWAY_API_KEY)"
        )
    ctx, citations = _design_digest(req.message)
    gw = HermesGateway(
        base_url=s.hermes_gateway_base_url,
        api_key=s.hermes_gateway_api_key,
        model=s.hermes_gateway_model,
        instructions=agents.apply_eda_skills(_RTL_ASSISTANT_INSTRUCTIONS) + ctx,
        timeout=s.hermes_gateway_timeout,
    )
    try:
        resp = await gw.run_async(req.message, user_id=req.user_id,
                                  session_id=req.session)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return ChatOut(content=resp.content, user_id=req.user_id, citations=citations)


# Serve the built SPA when present (production single-container mode).
_FRONTEND_DIST = _ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
