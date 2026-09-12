"""Environment configuration for the api-server.

The Hermes Gateway settings mirror ai_driven_rtl so the same locally-running
gateway (default http://127.0.0.1:8643/v1) can back both projects. The API key
is read from the environment only — it is never hard-coded here.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # python-dotenv optional; env may be set by the shell.
    pass


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    hermes_gateway_base_url: str
    hermes_gateway_api_key: str
    hermes_gateway_model: str
    hermes_gateway_timeout: float
    use_skills: bool = True

    @property
    def has_real_key(self) -> bool:
        return bool(self.hermes_gateway_api_key)

    @property
    def model_label(self) -> str:
        return self.hermes_gateway_model


def load_settings() -> Settings:
    return Settings(
        hermes_gateway_base_url=os.getenv(
            "HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8643/v1"
        ),
        # Accept either name; API_SERVER_KEY is what `rtlgateway` prints.
        hermes_gateway_api_key=os.getenv(
            "HERMES_GATEWAY_API_KEY", os.getenv("API_SERVER_KEY", "")
        ),
        hermes_gateway_model=os.getenv("HERMES_GATEWAY_MODEL", "hermes-agent"),
        hermes_gateway_timeout=float(os.getenv("HERMES_GATEWAY_TIMEOUT", "600")),
        # Tell agents to discover & apply the gateway's installed EDA skills
        # (systemverilog / fpga / ppa-closure-agent). Set HERMES_USE_SKILLS=0 to
        # fall back to skill-free prompts.
        use_skills=_env_flag("HERMES_USE_SKILLS", True),
    )


def sim_env(**extra: str) -> Dict[str, str]:
    """Environment for a cocotb `make`.

    cocotb embeds a Python interpreter through GPI and locates the venv from
    **VIRTUAL_ENV**, not from PATH — activation is what normally sets it. Running
    the api-server as `uvicorn api.server:app` from the venv without activating
    leaves it unset, so the embedded interpreter falls back to the system Python,
    fails to import `pygpi`, and never writes results.xml. The failure surfaces
    as "the regression failed" when in fact it never ran.

    PYTHONHOME is dropped for the same family of reason: a stale value points the
    embedded interpreter at the wrong stdlib. It is the known CI failure here.
    """
    env = {**os.environ, **extra}
    bindir = Path(sys.executable).parent
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    env.pop("PYTHONHOME", None)
    # sys.prefix differs from base_prefix exactly when we are inside a venv.
    if sys.prefix != sys.base_prefix:
        env["VIRTUAL_ENV"] = sys.prefix
    return env
