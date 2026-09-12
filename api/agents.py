"""Planner + reflection agents (improvements #4, #5 — LLM layer).

Spec2RTL-Agent's enabler #1 is a reasoning/understanding module that turns a
spec into a structured step-by-step implementation plan; enabler #3 is an
adaptive reflection module that traces the source of errors. Here both are thin
roles over the Hermes Gateway (api/hermes_engine.py).

NOTE: these require a configured gateway (HERMES_GATEWAY_API_KEY). Without it
the endpoints return 503, exactly like /chat. The deterministic, gateway-free
core of reflection lives in api/reflection.py and is what the sign-off loop
actually gates on; this LLM layer adds natural-language plans / explanations.
"""
from __future__ import annotations

from . import skills
from .config import load_settings
from .hermes_engine import HermesGateway

def apply_eda_skills(instructions: str) -> str:
    """Append the skills directive for the skills that are ACTUALLY installed.

    This used to name a hard-coded tuple ("systemverilog", "fpga",
    "ppa-closure-agent"). That silently misfires: the gateway serves one profile,
    and naming a skill the profile does not have tells the agent to load something
    that does not exist. `api/skills.py` resolves the serving profile and builds
    the directive from what is really there — see `GET /skills` for the live state
    and `scripts/sync_hermes_skills.py` to install what is missing.
    """
    return instructions + skills.directive()


PLANNER_INSTRUCTIONS = (
    "You are the reasoning/planning module of an AI-driven RTL flow. Input is a "
    "uArch document (existing + changed) and an algorithm reference in Python. "
    "Produce a structured, numbered step-by-step implementation plan for the "
    "RTL/SystemC: list modules and their interfaces (ready/valid, widths), the "
    "datapath and any FSM, the LUT/memory plan, the reset/clocking strategy, and "
    "the verification hooks (which golden patterns prove which behavior). When a "
    "'changed' section is given, mark each step as NEW / MODIFIED / UNCHANGED so "
    "downstream incremental regeneration touches only what changed. Be concise "
    "and concrete; do not emit RTL yet. Write the plan in the same language as "
    "the input (Korean in -> Korean plan, English in -> English plan), but ALWAYS "
    "keep the per-step tags as the English keywords NEW / MODIFIED / UNCHANGED "
    "(e.g. '3. MODIFIED: ...') so they stay machine-parseable."
)

REFLECTION_INSTRUCTIONS = (
    "You are the adaptive reflection module of an AI-driven RTL flow. Given a "
    "failure signal (lint error, synthesis failure, scoreboard mismatch, or "
    "formal counterexample) plus the implementation plan, identify the most "
    "likely SOURCE stage of the error (plan / C++ intermediate / RTL / testbench) "
    "and the specific segment to revisit, then propose a minimal corrective "
    "action. Prefer the deterministic stage classification you are given and "
    "explain it; do not hand-wave."
)


def _gateway(instructions: str, name: str) -> HermesGateway:
    s = load_settings()
    return HermesGateway(
        base_url=s.hermes_gateway_base_url,
        api_key=s.hermes_gateway_api_key,
        model=s.hermes_gateway_model,
        instructions=instructions,
        timeout=s.hermes_gateway_timeout,
        name=name,
    )


def build_planner() -> HermesGateway:
    return _gateway(apply_eda_skills(PLANNER_INSTRUCTIONS), "planner")


def build_reflector() -> HermesGateway:
    return _gateway(apply_eda_skills(REFLECTION_INSTRUCTIONS), "reflector")
