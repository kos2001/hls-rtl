"""Self-improvement loop — propose, prove against the oracle, reflect, retry.

This applies the project's own thesis to itself. An agent that edits RTL and then
grades its own work converges on plausibility; this loop cannot, because every
iteration is gated by the same 3-way bit-exact scoreboard that gates a human
change. A candidate is only "better" if the Python golden says the bytes match.

    goal / spec delta
          │
          ▼
      generate ──► prove ──► pass ──► candidate is provably equivalent
          ▲          │
          │          └─ fail ──► reflect (which stage, what evidence)
          └──────────────────────────┘   feedback, bounded retries

Two entry points, and the deterministic one matters most:

  * `prove(candidate)` — lint, design rules, synthesis, then the real cocotb
    regression run against the CANDIDATE file. No LLM anywhere in it. This is
    the gate, and it is verified to catch mutations: swapping a channel's LUT
    read produces `MISMATCH at idx=18 got=[199,0,255] ref=[186,0,255]`.
  * `run_loop(...)` — the LLM iteration that uses `prove` as its only judge.

  * `audit()` — the loop's other half: what evidence is MISSING. Deterministic,
    no gateway needed, and the honest answer to "what should improve next" when
    everything currently passes.

Safety: a candidate is written under `build/improve/`, never over `rtl/gamma.v`.
`apply()` is a separate, explicit step and refuses a candidate that did not pass.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import knowledge as kb, reflection, rtl_qor
from .config import load_settings, sim_env
from .hermes_engine import HermesGateway
from .telemetry import archive

_ROOT = Path(__file__).resolve().parents[1]
_TB = _ROOT / "tb"
_RTL = _ROOT / "rtl" / "gamma.v"
_WORK = _ROOT / "build" / "improve"
_FORMAL = _ROOT / "formal"

# "[edge_cases/env] RTL vs golden: OK (24 pixels, hash=c695...)"
# "[edge_cases/env] RTL vs golden: MISMATCH at idx=18 got=[199, 0, 255] ref=[186, 0, 255] (4/24 pixels differ)"
_PAT_RE = re.compile(
    r"\[(?P<pat>\w+)/(?P<prof>\w+)\]\s+RTL vs golden:\s+"
    r"(?:OK\s*\((?P<px>\d+) pixels, hash=(?P<hash>[0-9a-f]+)\)"
    r"|MISMATCH at idx=(?P<idx>\d+) got=(?P<got>\[[^\]]*\]) ref=(?P<ref>\[[^\]]*\])"
    r"\s*\((?P<bad>\d+)/(?P<tot>\d+) pixels differ\))"
)
_SUMMARY_RE = re.compile(r"TESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)")
# "[gradient/both_heavy] throughput: 11450 cycles / 2048 px = 5.590 cyc/px"
_TPUT_RE = re.compile(
    r"\[(?P<tag>[\w/]+)\] throughput: \d+ cycles / \d+ px = (?P<cpp>[\d.]+) cyc/px")


@dataclass
class PatternOutcome:
    name: str
    ok: bool
    pixels: int = 0
    sha256: str = ""
    first_bad_index: Optional[int] = None
    got: str = ""
    ref: str = ""
    differing: int = 0


@dataclass
class Proof:
    """The verdict on one candidate. `equivalent` is the only thing that counts."""
    candidate_path: str
    stages: Dict[str, str] = field(default_factory=dict)   # name -> pass/fail/skip
    details: Dict[str, str] = field(default_factory=dict)
    patterns: List[PatternOutcome] = field(default_factory=list)
    tests: Tuple[int, int, int] = (0, 0, 0)                # total, passed, failed
    # "pattern/profile" -> cyc/px. Carried as INFORMATION, not as a gate: a
    # measured comparison showed a one-entry occupancy error (effective depth 7
    # vs 8) produces 0.0% throughput difference on every profile, so a timing
    # threshold here would not catch the bug it looks like it catches.
    throughput: Dict[str, float] = field(default_factory=dict)
    elapsed_s: float = 0.0
    log_tail: str = ""

    @property
    def equivalent(self) -> bool:
        """Bit-exact against the golden oracle on every pattern that ran.

        Requires patterns to actually have run — an empty result is "no
        evidence", never "equivalent".
        """
        # `formal` may be `skip` (sby absent) without blocking a verdict, but a
        # formal FAILURE is disqualifying: it means a control-path invariant is
        # violated on some trace the test set simply never produced.
        return (bool(self.patterns)
                and all(p.ok for p in self.patterns)
                and self.stages.get("simulate") == "pass"
                and self.stages.get("4state") != "fail"
                and self.stages.get("formal") != "fail")

    #: What a PROVEN verdict does and does not license you to say. Carried on
    #: the object so the UI, the agent and the loop all repeat the same claim.
    PROVES = ("output values and their ordering are bit-exact against the Python "
              "golden model for the patterns and backpressure profiles that ran; "
              "— when the 4-state stage ran — that the same tests hold under a "
              "simulator that can represent X, so no uninitialised read or "
              "unreset register leaks into a sampled output; and — when the "
              "formal stage ran — that the handshake invariants hold on every "
              "trace up to the bounded depth: no overflow, no false "
              "backpressure, no retraction, output valid exactly when a pixel "
              "is outstanding")
    DOES_NOT_PROVE = (
        "behaviour beyond the formal bound (the induction case does not close, "
        "so this is a bounded proof, not an unbounded one), datapath values for "
        "inputs outside the test set, whether the test set would CATCH a bug at "
        "all (pass rate is not sensitivity), or anything about Fmax, area or "
        "power")

    @property
    def verdict(self) -> str:
        if self.equivalent:
            return "PROVEN"
        if any(self.stages.get(k) == "fail"
               for k in ("simulate", "4state", "formal")):
            return "REJECTED"
        return "INCONCLUSIVE"

    def to_dict(self) -> dict:
        return {
            "candidate_path": self.candidate_path,
            "verdict": self.verdict,
            "equivalent": self.equivalent,
            "stages": self.stages,
            "details": self.details,
            "tests": {"total": self.tests[0], "passed": self.tests[1], "failed": self.tests[2]},
            "elapsed_s": round(self.elapsed_s, 2),
            "patterns": [p.__dict__ for p in self.patterns],
            "throughput": self.throughput,
            "proves": self.PROVES,
            "does_not_prove": self.DOES_NOT_PROVE,
            "log_tail": self.log_tail,
        }

    def failure_evidence(self, limit: int = 4) -> str:
        """The concrete facts a next attempt needs — values, not adjectives."""
        lines: List[str] = []
        for name, status in self.stages.items():
            if status == "fail":
                lines.append(f"{name}: FAILED — {self.details.get(name, '')}")
        bad = [p for p in self.patterns if not p.ok][:limit]
        for p in bad:
            lines.append(
                f"pattern {p.name}: first mismatch at pixel index {p.first_bad_index}, "
                f"RTL produced {p.got} but the golden model requires {p.ref} "
                f"({p.differing} pixels differ)")
        if not lines:
            lines.append("no stage reported a failure, but the candidate was not proven "
                         "— check that the regression actually ran")
        return "\n".join(lines)


# --------------------------------------------------------------- the gate ----



def _run_regression(candidate: Path, timeout: int, bp_profile: str,
                    sim: str = "verilator") -> Tuple[str, int]:
    env = sim_env(BP_PROFILE=bp_profile)
    try:
        proc = subprocess.run(
            ["make", "-s", f"SIM={sim}", f"VERILOG_SOURCES={candidate}"],
            cwd=str(_TB), env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (f"TIMEOUT after {timeout}s", 124)
    return (proc.stdout + proc.stderr, proc.returncode)


def _run_4state(candidate: Path, timeout: int) -> Tuple[str, str]:
    """The same testbench under Icarus, which is 4-state.

    Verilator models every signal as 0/1, so a register that reset fails to
    clear simply starts at 0 and the bug is invisible. Demonstrated, not
    assumed: deleting `count <= 0` from the reset branch gives 5/5 PASS under
    Verilator and 0/5 under Icarus.

    One backpressure profile is enough here. An X does not depend on stall
    timing — it appears as soon as an uninitialised value is read — so paying
    for the full cross-product a second time buys nothing.
    """
    if shutil.which("iverilog") is None:
        return ("skip", "iverilog not available")
    log, rc = _run_regression(candidate, timeout, "single", sim="icarus")
    m = _SUMMARY_RE.search(log)
    if not m:
        tail = log.strip().splitlines()[-1:] or [""]
        return ("fail", f"could not parse icarus results — {tail[0][:120]}")
    total, passed, failed = (int(m.group(i)) for i in (1, 2, 3))
    ok = failed == 0 and rc == 0
    return ("pass" if ok else "fail",
            f"icarus: {passed}/{total} tests pass (4-state)")


def _parse_patterns(log: str) -> List[PatternOutcome]:
    """Collapse per-profile lines into one outcome per pattern.

    A pattern that mismatched under ANY profile is failed: backpressure changes
    ordering in time, never values, so a profile-dependent mismatch is a real
    bug and must not be averaged away.
    """
    by_name: Dict[str, PatternOutcome] = {}
    for m in _PAT_RE.finditer(log):
        name = m["pat"]
        cur = by_name.get(name)
        if m["hash"]:
            out = PatternOutcome(name=name, ok=True, pixels=int(m["px"]), sha256=m["hash"])
        else:
            out = PatternOutcome(
                name=name, ok=False, pixels=int(m["tot"]),
                first_bad_index=int(m["idx"]), got=m["got"], ref=m["ref"],
                differing=int(m["bad"]))
        if cur is None or (cur.ok and not out.ok):
            by_name[name] = out
    return list(by_name.values())


_SBY_DONE_RE = re.compile(r"DONE \((?P<status>[A-Z]+)")
_SBY_FAIL_RE = re.compile(r"failed assertion (?P<name>[\w.]+)")


def _run_formal(candidate: Path, timeout: int) -> Tuple[str, str]:
    """SymbiYosys over the control-path invariants, against the CANDIDATE.

    Closes a measured gap: a one-entry occupancy error passes the whole
    scoreboard with no throughput change, and `a_no_false_stall` catches it in
    under a second. `cover` runs too — a bounded proof that passes over
    unreachable states proves nothing, so reachability is part of the result,
    not a footnote.

    Bounded, not unbounded: see the note in formal/gamma.sby about induction.
    """
    if shutil.which("sby") is None:
        return ("skip", "sby not available")
    if not (_FORMAL / "gamma.sby").exists():
        return ("skip", "formal/gamma.sby not found")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shutil.copy2(_FORMAL / "gamma_props.sv", work / "gamma_props.sv")
        shutil.copy2(candidate, work / "gamma.v")
        sby = (_FORMAL / "gamma.sby").read_text().replace("../rtl/gamma.v", "gamma.v")
        (work / "gamma.sby").write_text(sby)

        results, failures = {}, []
        for task in ("bmc", "cover"):
            try:
                proc = subprocess.run(
                    ["sby", "-f", "gamma.sby", task], cwd=str(work),
                    env=sim_env(), capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                return ("fail", f"{task} timed out after {timeout}s")
            except OSError as exc:
                return ("skip", str(exc))
            out = proc.stdout + proc.stderr
            m = _SBY_DONE_RE.search(out)
            results[task] = m["status"] if m else "ERROR"
            failures += [f"{task}:{f}" for f in set(_SBY_FAIL_RE.findall(out))]

        ok = all(v == "PASS" for v in results.values())
        detail = ", ".join(f"{k}={v}" for k, v in results.items())
        if failures:
            detail += " — " + "; ".join(sorted(failures)[:4])
        return ("pass" if ok else "fail", detail)


def prove(candidate_verilog: Optional[str] = None, *, name: str = "",
          timeout: int = 600, bp_profile: str = "single",
          run_regression: bool = True, run_formal: bool = True,
          run_4state: bool = True) -> Proof:
    """Gate a candidate: static checks, then the real scoreboard against it.

    `candidate_verilog=None` proves the project RTL itself — the baseline, and a
    sanity check that the gate agrees with the committed state.
    """
    code = candidate_verilog if candidate_verilog is not None else _RTL.read_text()
    _WORK.mkdir(parents=True, exist_ok=True)
    path = _WORK / f"{name or 'candidate'}-{uuid.uuid4().hex[:8]}.v"
    path.write_text(code)

    t0 = time.time()
    proof = Proof(candidate_path=str(path.relative_to(_ROOT)))

    # 1. lint
    lint = rtl_qor.lint(code)
    if not lint.available:
        proof.stages["lint"] = "skip"
        proof.details["lint"] = "verilator not available"
    else:
        proof.stages["lint"] = "pass" if lint.ok else "fail"
        proof.details["lint"] = (f"{len(lint.issues)} finding(s): "
                                 + "; ".join(lint.issues[:3])) if lint.issues else "clean"

    # 2. design rules + 3. synthesis (one analyze pass provides both)
    report = rtl_qor.analyze(code)
    errs = [c for c in report.checks if c.severity == "error" and not c.ok
            and c.id not in ("synthesizable", "lint_clean")]
    proof.stages["design"] = "fail" if errs else "pass"
    proof.details["design"] = "; ".join(c.detail for c in errs) or "structural checks ok"

    synth = report.metrics.get("synthesizable")
    if synth is None:
        proof.stages["synthesize"] = "skip"
        proof.details["synthesize"] = "yosys not available"
    else:
        proof.stages["synthesize"] = "pass" if synth else "fail"
        proof.details["synthesize"] = (f"cells={report.metrics.get('synth_cells')} "
                                       f"flops={report.metrics.get('synth_flops')} "
                                       f"latches={report.metrics.get('synth_latches')}")

    # 4. the oracle. Skipped only when the earlier stages make it meaningless —
    # a candidate that does not lint cannot be simulated, and reporting that as
    # "not equivalent" would hide the real cause.
    blocked = proof.stages.get("lint") == "fail" or proof.stages.get("design") == "fail"
    if not run_regression:
        proof.stages["simulate"] = "skip"
        proof.details["simulate"] = "regression not requested"
    elif blocked:
        proof.stages["simulate"] = "skip"
        proof.details["simulate"] = "not run — an earlier gating stage failed"
    elif not rtl_qor.verilator_available():
        proof.stages["simulate"] = "skip"
        proof.details["simulate"] = "verilator not available"
    else:
        log, rc = _run_regression(path, timeout, bp_profile)
        proof.log_tail = log[-3000:]
        proof.patterns = _parse_patterns(log)
        proof.throughput = {m["tag"]: float(m["cpp"]) for m in _TPUT_RE.finditer(log)}
        m = _SUMMARY_RE.search(log)
        if m:
            proof.tests = (int(m[1]), int(m[2]), int(m[3]))
            ok = proof.tests[2] == 0 and rc == 0 and all(p.ok for p in proof.patterns)
            proof.stages["simulate"] = "pass" if ok else "fail"
            proof.details["simulate"] = (
                f"{proof.tests[1]}/{proof.tests[0]} cocotb tests, "
                f"{sum(p.ok for p in proof.patterns)}/{len(proof.patterns)} patterns bit-exact")
        else:
            proof.stages["simulate"] = "fail"
            proof.details["simulate"] = "could not parse cocotb results"

    # 5. 4-state. The same tests, under a simulator that can represent X.
    if run_4state and not blocked and proof.stages.get("simulate") == "pass":
        st, detail = _run_4state(path, timeout=timeout)
        proof.stages["4state"] = st
        proof.details["4state"] = detail
    elif run_4state:
        proof.stages["4state"] = "skip"
        proof.details["4state"] = ("not run — the 2-state regression must pass first"
                                   if not blocked else
                                   "not run — an earlier gating stage failed")

    # 6. formal. Independent of the scoreboard on purpose: it is here precisely
    #    to cover what simulation provably cannot see.
    if run_formal and not blocked:
        st, detail = _run_formal(path, timeout=timeout)
        proof.stages["formal"] = st
        proof.details["formal"] = detail
    elif run_formal:
        proof.stages["formal"] = "skip"
        proof.details["formal"] = "not run — an earlier gating stage failed"

    proof.elapsed_s = time.time() - t0
    return proof


def apply_candidate(candidate_path: str, *, backup: bool = True) -> dict:
    """Promote a PROVEN candidate to rtl/gamma.v.

    Re-proves it here rather than trusting a caller-supplied verdict: the file
    could have changed since, and "it passed earlier" is not evidence about the
    bytes being installed now.
    """
    p = (_ROOT / candidate_path).resolve()
    if _WORK.resolve() not in p.parents:
        raise ValueError("candidate must live under build/improve/")
    if not p.exists():
        raise FileNotFoundError(candidate_path)

    proof = prove(p.read_text(), name="preapply")
    if not proof.equivalent:
        return {"applied": False, "reason": "candidate is not proven equivalent",
                "proof": proof.to_dict()}

    backup_path = ""
    if backup:
        backup_path = str((_RTL.parent / f"gamma.v.bak-{time.strftime('%Y%m%d-%H%M%S')}")
                          .relative_to(_ROOT))
        shutil.copy2(_RTL, _ROOT / backup_path)
    shutil.copy2(p, _RTL)
    return {"applied": True, "backup": backup_path, "proof": proof.to_dict()}


# ------------------------------------------------------------- the auditor ---
_GAP_CHECKS = (
    ("4-state simulation", "high",
     "The main regression runs under Verilator, which is 2-state: it cannot "
     "represent X, so an unreset register simply starts at 0. Deleting "
     "`count <= 0` from the reset branch gives 5/5 PASS under Verilator and 0/5 "
     "under Icarus — measured, not argued. The gate runs Icarus when it is "
     "installed; without it this evidence is missing.",
     "make -C tb SIM=icarus"),
    ("unbounded formal proof", "medium",
     "formal/ covers the handshake invariants, but only to a BOUNDED depth: "
     "k-induction's base case passes and the induction step does not, because "
     "linking the reference occupancy counter to the DUT's internal counter "
     "needs a hierarchical reference yosys does not support. Traces longer than "
     "the bound are unproven.",
     "strengthen the invariant (e.g. expose occupancy as a port, or use a "
     "toolchain with hierarchical access), then: sby -f formal/gamma.sby prove"),
    ("mutation coverage", "medium",
     "Nothing measures whether the testbench would CATCH a bug. Pass rate is "
     "not sensitivity.",
     "mcy init && mcy run"),
    ("systemc rung", "medium",
     "build/sc_out.txt absent, so the SystemC representation is unproven; only "
     "two of the three models are actually compared.",
     "build the SystemC sim, then ./scripts/run_3way.sh"),
    ("code coverage", "low",
     "No line/branch coverage, so it is unknown which RTL the 13 patterns "
     "actually reach.",
     "verilator --coverage ... && verilator_coverage --write-info"),
    ("style lint", "low",
     "verilator --lint-only checks semantics, not house style; no formatter is "
     "enforced.",
     "verible-verilog-lint / verible-verilog-format"),
)


def audit() -> dict:
    """What evidence is missing — the honest answer to "improve what next?".

    Deliberately deterministic and gateway-free. When everything passes, the
    useful next step is never "generate more RTL", it is "close an evidence gap",
    and that judgement should not depend on an LLM being reachable.
    """
    have_sc = (_ROOT / "build" / "sc_out.txt").exists()
    have_icarus = shutil.which("iverilog") is not None
    have_sby = shutil.which("sby") is not None
    have_formal = (_FORMAL / "gamma.sby").exists()
    have_verible = shutil.which("verible-verilog-lint") is not None
    have_mcy = shutil.which("mcy") is not None

    satisfied = {"systemc rung": have_sc, "4-state simulation": have_icarus}
    tooling = {
        "4-state simulation": have_icarus,
        "unbounded formal proof": have_sby and have_formal,
        "mutation coverage": have_mcy,
        "style lint": have_verible,
    }

    gaps = []
    for name, severity, why, how in _GAP_CHECKS:
        if satisfied.get(name):
            continue
        gaps.append({
            "gap": name,
            "severity": severity,
            "why_it_matters": why,
            "how_to_close": how,
            "tool_installed": tooling.get(name, True),
        })
    rank = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (rank[g["severity"]], not g["tool_installed"]))
    return {
        "gaps": gaps,
        "note": "These are gaps in EVIDENCE, not known defects. A passing "
                "scoreboard bounds what is proven; it does not enlarge it.",
    }


# ---------------------------------------------------------------- the loop ---
_GENERATOR_INSTRUCTIONS = (
    "You are the RTL generation module of a closed verification loop. You are "
    "given the current Verilog, a goal, and — if a previous attempt failed — the "
    "exact evidence of how it failed.\n"
    "Rules:\n"
    "1. Output ONE complete Verilog-2001 module in a single ```verilog fenced "
    "block. No prose outside the block. The module must be named `gamma` and "
    "keep its port list byte-compatible: the testbench binds to these names.\n"
    "2. Portable Verilog-2001 only — `reg`/`wire`/`always @`. Do not use "
    "SystemVerilog constructs; the flow runs TOPLEVEL_LANG=verilog.\n"
    "3. Values and ordering are fixed by the Python golden model. If the goal is "
    "a timing or structural change, the output bytes must not move.\n"
    "4. When you are given failure evidence, address THAT evidence. Do not "
    "rewrite unrelated logic; a smaller diff is easier to prove.\n"
    "5. Preserve the existing header comment block and update it if the "
    "contract changed."
)

_CODE_RE = re.compile(r"```(?:verilog|systemverilog|v)?\s*\n(.*?)```", re.S)


def _extract_module(text: str) -> Optional[str]:
    blocks = _CODE_RE.findall(text)
    for b in blocks:
        if "module gamma" in b and "endmodule" in b:
            return b.strip() + "\n"
    return None


def _gateway(instructions: str, name: str) -> HermesGateway:
    s = load_settings()
    return HermesGateway(
        base_url=s.hermes_gateway_base_url, api_key=s.hermes_gateway_api_key,
        model=s.hermes_gateway_model, instructions=instructions,
        timeout=s.hermes_gateway_timeout, name=name,
    )


async def run_loop(goal: str, *, max_iters: int = 3, bp_profile: str = "single",
                   timeout: int = 600, user_id: str = "default-user") -> dict:
    """Propose → prove → reflect, bounded, with the oracle as the only judge.

    Returns every attempt, including the failures. A loop that reports only its
    successes teaches nothing about whether it is working.
    """
    s = load_settings()
    if not s.has_real_key:
        return {"ok": False, "error": "Hermes Gateway credentials missing "
                                      "(set HERMES_GATEWAY_API_KEY)"}

    baseline = prove(name="baseline", timeout=timeout, bp_profile=bp_profile)
    current_rtl = _RTL.read_text()
    attempts: List[dict] = []
    feedback: Optional[str] = None
    proven: Optional[dict] = None

    for i in range(1, max_iters + 1):
        ctx, citations = kb.context_for(goal + ("\n" + feedback if feedback else ""),
                                        budget=7000)
        prompt = (
            f"GOAL:\n{goal}\n\n"
            f"CURRENT rtl/gamma.v:\n```verilog\n{current_rtl}\n```\n"
        )
        if feedback:
            prompt += (
                f"\nATTEMPT {i - 1} WAS REJECTED BY THE ORACLE. Evidence:\n{feedback}\n"
                "Fix exactly this. The golden model is authoritative — if the RTL "
                "and the golden disagree, the RTL is wrong.\n"
            )
        gw = _gateway(_GENERATOR_INSTRUCTIONS + ctx, f"generator-{i}")
        try:
            resp = await gw.run_async(prompt, user_id=user_id,
                                      session_id=uuid.uuid4().hex)
        except RuntimeError as exc:
            attempts.append({"iteration": i, "error": str(exc)})
            break

        code = _extract_module(resp.content)
        if code is None:
            attempts.append({
                "iteration": i, "error": "no complete `module gamma` in the reply",
                "reply_head": resp.content[:400],
            })
            feedback = ("Your previous reply contained no complete Verilog module. "
                        "Output exactly one ```verilog block containing `module gamma` "
                        "through `endmodule`.")
            continue

        proof = prove(code, name=f"iter{i}", timeout=timeout, bp_profile=bp_profile)
        diff_lines = _diff_stat(current_rtl, code)
        # Did this attempt actually change anything? A generator that reverts to
        # the committed RTL will pass the oracle trivially — that is not progress
        # toward the goal, and counting it as convergence is exactly the
        # self-deception this project exists to prevent.
        changed = _normalise(code) != _normalise(current_rtl)
        record = {
            "iteration": i,
            "proof": proof.to_dict(),
            "diff": diff_lines,
            "changed_rtl": changed,
            "citations": citations,
        }
        attempts.append(record)

        if proof.equivalent and changed:
            proven = record
            break
        if proof.equivalent and not changed:
            # Proven, but it is the baseline. Say so and stop: asking again just
            # burns budget on a generator that has already given up on the goal.
            record["note"] = ("candidate is byte-identical to the committed RTL — "
                              "the goal was not implemented")
            break

        feedback = proof.failure_evidence()
        stages = {k: v for k, v in proof.stages.items()}
        record["reflection"] = reflection.classify(stages)

    outcome, summary = _classify_outcome(attempts, proven, max_iters)
    result = {
        "ok": True,
        "goal": goal,
        "iterations_run": len(attempts),
        "max_iters": max_iters,
        "baseline": baseline.to_dict(),
        "attempts": attempts,
        "outcome": outcome,
        "summary": summary,
        # Kept for compatibility, but it now means what it says: a PROVEN
        # candidate that actually changed the RTL.
        "converged": outcome == "PROVEN_CHANGE",
        "proven_candidate": proven["proof"]["candidate_path"] if proven else None,
        "proves": Proof.PROVES,
        "does_not_prove": Proof.DOES_NOT_PROVE,
        "note": "A proven candidate is bit-exact against the Python golden on "
                "every pattern that ran. It is NOT applied — call /improve/apply.",
    }
    archive.record("improve", {
        "goal": goal[:120],
        "outcome": outcome,
        "iterations": len(attempts),
        "score": 100 if outcome == "PROVEN_CHANGE" else 0,
    })
    return result


def _normalise(code: str) -> str:
    """Compare RTL ignoring whitespace and comments, so a reformat or a reworded
    header is not mistaken for a functional change."""
    no_block = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    return re.sub(r"\s+", " ", no_line).strip()


#: What the loop actually achieved. A boolean could not distinguish "it worked"
#: from "it gave up and the baseline passed", and those need different responses.
_OUTCOMES = {
    "PROVEN_CHANGE": "A changed RTL is bit-exact against the golden model.",
    "ORACLE_CONFLICT": (
        "Every attempt that implemented the goal was rejected by the oracle on "
        "VALUES, and the run ended at the unchanged baseline. The goal as stated "
        "contradicts the golden model: change the golden model first if the new "
        "behaviour is intended, or restate the goal."),
    "NO_CHANGE": (
        "The loop ended with RTL identical to the committed file. The goal was "
        "not implemented — this is not a pass."),
    "EXHAUSTED": "The iteration budget ran out with no proven candidate.",
    "ERRORED": "The loop stopped on a generator or gateway error.",
}


def _classify_outcome(attempts: List[dict], proven: Optional[dict],
                      max_iters: int) -> Tuple[str, str]:
    if proven is not None:
        return "PROVEN_CHANGE", _OUTCOMES["PROVEN_CHANGE"]
    if attempts and "error" in attempts[-1]:
        return "ERRORED", _OUTCOMES["ERRORED"]

    reverted = any(a.get("proof", {}).get("equivalent") and not a.get("changed_rtl")
                   for a in attempts)
    functional_reject = any(
        a.get("proof", {}).get("stages", {}).get("simulate") == "fail"
        and a.get("changed_rtl")
        for a in attempts)
    if reverted and functional_reject:
        return "ORACLE_CONFLICT", _OUTCOMES["ORACLE_CONFLICT"]
    if reverted:
        return "NO_CHANGE", _OUTCOMES["NO_CHANGE"]
    return "EXHAUSTED", _OUTCOMES["EXHAUSTED"]


def _diff_stat(old: str, new: str) -> dict:
    import difflib
    a, b = old.splitlines(), new.splitlines()
    added = removed = 0
    hunks: List[str] = []
    for line in difflib.unified_diff(a, b, lineterm="", n=1):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
        if len(hunks) < 60:
            hunks.append(line)
    return {"added": added, "removed": removed, "unified": "\n".join(hunks)}
