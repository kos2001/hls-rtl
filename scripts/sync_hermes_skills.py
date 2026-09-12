#!/usr/bin/env python3
"""Install this repo's EDA skills into the Hermes profile backing the gateway.

The repo is the source of truth (`skills/<category>/<name>/SKILL.md`); the hermes
profile is a deploy target. Keeping it that way means skills are reviewable in git
instead of living only in ~/.hermes.

Also back-fills stock skills (`systemverilog`, `fpga`) that this project's agents
expect but the serving profile lacks, by copying them from another local profile
that already has them — no network, no re-authoring.

Safety: additive by default. An existing file is only replaced with --force, and
is backed up to <name>.bak-<timestamp> first. Nothing is ever deleted.

Usage:
    python scripts/sync_hermes_skills.py --list
    python scripts/sync_hermes_skills.py --dry-run
    python scripts/sync_hermes_skills.py
    python scripts/sync_hermes_skills.py --profile rtlgateway --force
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import skills as skills_mod  # noqa: E402

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
REPO_SKILLS = Path(__file__).resolve().parents[1] / "skills"
# Stock skills the project wants but does not author; sourced from a sibling profile.
BACKFILL = ("systemverilog", "fpga")


def _profile_dir(profile: str) -> Path:
    return HERMES_HOME / "profiles" / profile / "skills"


def _repo_sources() -> List[Tuple[str, str, Path]]:
    """(category, name, dir) for every skill authored in this repo."""
    out = []
    for md in sorted(REPO_SKILLS.rglob("SKILL.md")):
        rel = md.parent.relative_to(REPO_SKILLS)
        if len(rel.parts) != 2:
            continue  # expected layout is <category>/<name>/SKILL.md
        out.append((rel.parts[0], rel.parts[1], md.parent))
    return out


def _find_backfill(name: str, exclude: str) -> Optional[Path]:
    """Any other local profile that already ships `name`, newest first."""
    root = HERMES_HOME / "profiles"
    if not root.is_dir():
        return None
    cands = [p.parent for p in root.glob(f"*/skills/*/{name}/SKILL.md")
             if exclude not in p.parts and ".archive" not in p.parts]
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _install(src: Path, dst: Path, *, force: bool, dry: bool) -> str:
    """Copy a skill directory. Returns a one-word outcome for the report."""
    md = dst / "SKILL.md"
    if md.exists():
        if not force:
            return "exists"
        if not dry:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.move(str(md), str(dst / f"SKILL.md.bak-{stamp}"))
        outcome = "replaced"
    else:
        outcome = "installed"
    if not dry:
        dst.mkdir(parents=True, exist_ok=True)
        # copy the whole skill dir (references/, scripts/ travel with SKILL.md)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return outcome


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="target profile (default: the one serving the gateway)")
    ap.add_argument("--dry-run", action="store_true", help="show what would change")
    ap.add_argument("--force", action="store_true", help="overwrite (backs up first)")
    ap.add_argument("--list", action="store_true", help="report current state and exit")
    ap.add_argument("--no-backfill", action="store_true",
                    help="skip copying stock skills from sibling profiles")
    args = ap.parse_args(list(argv) if argv is not None else None)

    rep = skills_mod.report(args.profile, refresh=True)
    profile = args.profile or rep.profile
    if not profile:
        print("error: could not resolve the profile serving "
              f"{rep.gateway_base_url}. Pass --profile or set HERMES_PROFILE.",
              file=sys.stderr)
        return 2

    print(f"gateway : {rep.gateway_base_url}")
    print(f"profile : {profile}")
    print(f"target  : {_profile_dir(profile)}")
    print()
    for s in rep.skills:
        mark = "OK " if s.installed else "-- "
        print(f"  {mark} {s.name:32} {s.source:10} {s.purpose}")
    if args.list:
        return 0

    target = _profile_dir(profile)
    print(f"\n{'DRY RUN — no files written' if args.dry_run else 'syncing'}\n")
    results: List[Tuple[str, str]] = []

    for category, name, src in _repo_sources():
        results.append((name, _install(src, target / category / name,
                                       force=args.force, dry=args.dry_run)))

    if not args.no_backfill:
        for name in BACKFILL:
            if any(s.name == name and s.installed for s in rep.skills):
                results.append((name, "exists"))
                continue
            src = _find_backfill(name, exclude=profile)
            if src is None:
                results.append((name, "unavailable"))
                continue
            results.append((name, _install(src, target / src.parent.name / name,
                                           force=args.force, dry=args.dry_run)))

    width = max(len(n) for n, _ in results)
    for name, outcome in results:
        print(f"  {name:{width}}  {outcome}")

    if not args.dry_run:
        after = skills_mod.report(args.profile, refresh=True)
        print(f"\nactive now : {', '.join(after.active) or '(none)'}")
        if after.missing:
            print(f"still missing: {', '.join(after.missing)}")
        print("\nRestart the gateway for the agent to pick up new skills:")
        print(f"  hermes --profile {profile} gateway restart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
