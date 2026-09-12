"""Live discovery of the Hermes Agent skills the gateway can actually load.

`api/agents.py` used to hard-code the skill names it told the agent to load. That
is a silent failure mode: the gateway serves ONE profile, and if that profile does
not have a named skill the directive becomes an instruction to load something that
does not exist — the agent either ignores it or invents the guidance.

So: resolve the profile that is actually serving the configured gateway URL, list
its installed skills, and build the directive from the intersection with what this
project wants. What is missing is reported, not silently dropped.

Skill layout (hermes-agent): <profile>/skills/<category>/<name>/SKILL.md
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .config import load_settings

_HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
_REPO_SKILLS = Path(__file__).resolve().parents[1] / "skills"

# Skills this project wants the agent grounded in, in priority order. The first
# three are authored in this repo (skills/); the rest are stock hermes EDA skills.
DESIRED_SKILLS: tuple[str, ...] = (
    "gamma-bitexact-verification",
    "rtl-verification-opensource",
    "eda-transcript-conventions",
    "systemverilog",
    "fpga",
    "ppa-closure-agent",
)

# Why each skill is wanted — shown in the UI so a missing skill is legible.
SKILL_PURPOSE: Dict[str, str] = {
    "gamma-bitexact-verification": "DUT contract, Δ-propagation drill, sign-off ladder",
    "rtl-verification-opensource": "tool selection: verilator/icarus/cocotb/sby/verible",
    "eda-transcript-conventions": "severity-tagged findings for the transcript console",
    "systemverilog": "RTL coding standards, synthesizable constructs",
    "fpga": "synthesis / timing / resource closure",
    "ppa-closure-agent": "power / performance / area trade-offs",
}


@dataclass
class SkillInfo:
    name: str
    category: str
    description: str
    installed: bool
    source: str  # "profile" | "repo-only" | "missing"
    purpose: str = ""


@dataclass
class SkillReport:
    profile: Optional[str]
    profile_dir: Optional[str]
    gateway_base_url: str
    use_skills: bool
    skills: List[SkillInfo] = field(default_factory=list)

    @property
    def active(self) -> List[str]:
        return [s.name for s in self.skills if s.installed]

    @property
    def missing(self) -> List[str]:
        return [s.name for s in self.skills if not s.installed]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "profile_dir": self.profile_dir,
            "gateway_base_url": self.gateway_base_url,
            "use_skills": self.use_skills,
            "active": self.active,
            "missing": self.missing,
            "skills": [s.__dict__ for s in self.skills],
        }


def _port_from_url(url: str) -> Optional[int]:
    try:
        p = urlparse(url)
        return p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        return None


def _profile_serving(port: int) -> Optional[str]:
    """Which `hermes ... --profile X gateway run` owns `port`?

    lsof gives the pid holding the listening socket; the profile is a flag on that
    process's command line. Best-effort: any failure just means "unknown profile",
    which degrades to repo-only skill reporting rather than an error.
    """
    try:
        pid = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
        if not pid:
            return None
        cmd = subprocess.run(["ps", "-p", pid[0], "-o", "command="],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"--profile[= ]+(\S+)", cmd) or re.search(r"\s-p\s+(\S+)", cmd)
    return m.group(1) if m else None


def _read_front_matter(skill_md: Path) -> Dict[str, str]:
    """Parse the leading `---` YAML block. Only name/description are needed, so a
    line-wise reader beats pulling in a YAML dependency."""
    out: Dict[str, str] = {}
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    if not text.startswith("---"):
        return out
    _, _, rest = text.partition("\n")
    body, _, _ = rest.partition("\n---")
    for line in body.splitlines():
        k, sep, v = line.partition(":")
        if sep and not k.startswith(" "):
            out[k.strip()] = v.strip()
    return out


def _index(root: Path) -> Dict[str, tuple[str, str]]:
    """name -> (category, description) for every SKILL.md under `root`.

    `.archive/` is hermes' disabled-skill graveyard — an archived skill is not
    loadable, so it must not count as installed.
    """
    found: Dict[str, tuple[str, str]] = {}
    if not root.is_dir():
        return found
    for md in root.rglob("SKILL.md"):
        rel = md.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        fm = _read_front_matter(md)
        name = fm.get("name") or md.parent.name
        category = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        found[name] = (category, fm.get("description", ""))
    return found


def _report_uncached(profile_override: Optional[str]) -> SkillReport:
    s = load_settings()
    profile = profile_override or os.getenv("HERMES_PROFILE")
    if not profile:
        port = _port_from_url(s.hermes_gateway_base_url)
        profile = _profile_serving(port) if port else None

    profile_dir = _HERMES_HOME / "profiles" / profile if profile else None
    installed = _index(profile_dir / "skills") if profile_dir else {}
    # Skills shipped with hermes itself, shared across profiles.
    installed.update({k: v for k, v in _index(_HERMES_HOME / "skills").items()
                      if k not in installed})
    repo = _index(_REPO_SKILLS)

    skills: List[SkillInfo] = []
    for name in DESIRED_SKILLS:
        if name in installed:
            cat, desc = installed[name]
            src = "profile"
            ok = True
        elif name in repo:
            cat, desc = repo[name]
            src = "repo-only"   # authored here but not synced to the gateway yet
            ok = False
        else:
            cat, desc, src, ok = "semiconductor-eda", "", "missing", False
        skills.append(SkillInfo(name=name, category=cat, description=desc,
                                installed=ok, source=src,
                                purpose=SKILL_PURPOSE.get(name, "")))
    return SkillReport(
        profile=profile,
        profile_dir=str(profile_dir) if profile_dir else None,
        gateway_base_url=s.hermes_gateway_base_url,
        use_skills=s.use_skills,
        skills=skills,
    )


@lru_cache(maxsize=4)
def _cached(profile_override: Optional[str]) -> SkillReport:
    return _report_uncached(profile_override)


def report(profile: Optional[str] = None, refresh: bool = False) -> SkillReport:
    """Skill availability for the profile backing the configured gateway.

    Cached because it shells out to lsof/ps and walks the skill tree; `refresh`
    re-scans after a sync so the UI can show the new state without a restart.
    """
    if refresh:
        _cached.cache_clear()
    return _cached(profile)


def directive() -> str:
    """The `skills` tool directive, naming only skills that are really installed.

    Returns "" when skills are disabled or none of the wanted ones are present —
    an empty directive is correct; instructing the agent to load a skill that does
    not exist is worse than saying nothing.
    """
    rep = report()
    if not rep.use_skills or not rep.active:
        return ""
    listed = ", ".join(f"`{n}`" for n in rep.active)
    return (
        "\n\nBefore answering, use your `skills` tool to load and apply this "
        f"gateway's skills: {listed}. Ground your answer in their guidance; when "
        "they conflict with the CURRENT DESIGN STATE below, the design state wins."
    )
