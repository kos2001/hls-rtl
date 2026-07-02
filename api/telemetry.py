"""Run archival + trend aggregation.

Records each significant run (sign-off, verification) as a small JSON summary
under runs/<kind>/ (gitignored) so quality can be tracked over time. Payloads
are summaries only (verdict, score, counts), never full RTL. Writes degrade to
a no-op on any I/O error so telemetry never breaks a request.

Ported from ai_driven_rtl/src/telemetry.py.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = _ROOT / "runs"


def _enabled() -> bool:
    return os.getenv("RTL_TELEMETRY", "1").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RunArchive:
    runs_dir: Path = DEFAULT_RUNS_DIR

    def record(self, kind: str, summary: Dict[str, Any]) -> Optional[Path]:
        if not _enabled():
            return None
        try:
            ts = time.time()
            rid = f"{int(ts)}-{os.getpid()}"
            d = self.runs_dir / kind
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{rid}.json"
            path.write_text(json.dumps({"kind": kind, "ts": ts, "run_id": rid, **summary},
                                       ensure_ascii=False, indent=2))
            return path
        except Exception:
            return None

    def load(self, kind: str) -> List[Dict[str, Any]]:
        d = self.runs_dir / kind
        if not d.is_dir():
            return []
        out: List[Dict[str, Any]] = []
        for f in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(f.read_text()))
            except Exception:
                continue
        return out

    def summary(self, kind: str) -> Dict[str, Any]:
        records = self.load(kind)
        agg: Dict[str, Any] = {"kind": kind, "count": len(records)}
        if not records:
            return agg
        verdicts: Dict[str, int] = {}
        scores: List[float] = []
        history: List[Dict[str, Any]] = []
        for r in records:
            v = r.get("verdict") or r.get("status")
            if v:
                verdicts[v] = verdicts.get(v, 0) + 1
            if isinstance(r.get("score"), (int, float)):
                scores.append(float(r["score"]))
            history.append({"ts": r.get("ts"), "verdict": v, "score": r.get("score")})
        agg["verdicts"] = verdicts
        if scores:
            agg["mean_score"] = round(sum(scores) / len(scores), 2)
            agg["last_score"] = scores[-1]
        agg["history"] = history[-20:]
        return agg


archive = RunArchive()
