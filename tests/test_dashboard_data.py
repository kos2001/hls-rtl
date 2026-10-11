"""The dashboard must distinguish reference output from measured evidence."""
import numpy as np

import test_set
from gamma_golden import apply_gamma, build_lut, frame_hash
from gen_dashboard_data import build_results


def test_generated_results_are_reference_only(monkeypatch):
    monkeypatch.delenv("GAMMA", raising=False)
    results = build_results()
    assert results["evidence_kind"] == "reference"
    assert results["gammas"] == test_set.DEFAULT_GAMMAS
    assert results["summary"]["total_patterns"] == len(test_set.patterns())
    assert all(row["sc_sha256"] is None for row in results["patterns"])


def test_gamma_metadata_describes_the_hashed_outputs(monkeypatch):
    monkeypatch.setenv("GAMMA", "1.5")
    results = build_results()
    assert results["gammas"] == {"r": 1.5, "g": 1.5, "b": 1.5}
    lut = build_lut(1.5)
    frame = test_set.patterns()["edge_cases"]
    expected = apply_gamma(frame, lut, lut, lut).reshape(-1, 3).astype(np.uint16)
    row = next(row for row in results["patterns"] if row["name"] == "edge_cases")
    assert row["golden_sha256"] == frame_hash(expected)
