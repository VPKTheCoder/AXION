"""Legacy adapter: binds validators to actual Scripts/core.py truth (P1.4).

These tests import the real legacy core (side-effect free) and pin the
Phase 0 code-fact findings as executed checks: the empty Gradient allowed
set (R-04), the unresolved Gradient SLO conflict (D-03), and the in-process
simulation-import ban.
"""

import pytest

from axion.config.legacy_config import load_core, serialize_cfg
from axion.constraints import legacy_adapter as LA

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "Scripts"


def _core():
    return load_core(SCRIPTS)


def test_core_loads_and_serializes():
    core = _core()
    cfg = serialize_cfg(core)
    assert cfg["N_NODES"] == 32 and cfg["N_RACKS"] == 4
    assert cfg["_derived"]["ALLOWED_CAPS"][0] == [1.0, 0.85]


def test_gradient_cap_exemption_reproduced():
    # Phase 0 R-04 CORRECTED (see audit_phase1/BASELINE_PRESERVATION.md §8):
    # the audit's stdlib re-derivation assumed Gradient was SLO-bound and
    # predicted ALLOWED_CAPS[5] == []. The code fact is the opposite: legacy
    # exempts Gradient from SLO_SENSITIVE, so it receives the FULL cap list
    # even though W_LAT[5]=24ms > L_MAX=19.5ms (L_eff up to 60ms at cap 0.40).
    # TATS's SA objective contradicts this exemption (it inf-rejects any
    # W_LAT > L_MAX); the three-way inconsistency stands, mechanism corrected.
    core = _core()
    caps = LA.allowed_caps(core)
    assert caps[5] == [1.0, 0.85, 0.7, 0.55, 0.4]
    assert [float(v) for v in core.W_LAT][5] == 24.0
    assert 5 not in [int(w) for w in core.CFG["SLO_SENSITIVE"]]
    assert caps[0] == [1.0, 0.85] and caps[1] == [1.0]


def test_gradient_slo_unresolved_not_invented():
    core = _core()
    table = LA.build_legacy_slo_table(core)
    grad = table[5]
    assert grad.slo_applies is None  # neither exempted nor bound by us
    assert "D-03" in grad.reason
    # Others follow legacy SLO_SENSITIVE exactly.
    assert [w.slo_applies for w in table[:5]] == [True] * 5


def test_legacy_slo_scores_candidate_and_baseline_steps():
    core = _core()
    # All-Embed at cap 1.0: decidable workloads pass, Gradient unresolved.
    rep = LA.check_step_slo(core, [4] * 32, [1.0] * 32)
    assert rep.verdict == "PASS" and rep.undetermined == []
    rep = LA.check_step_slo(core, [5] * 32, [1.0] * 32)
    assert rep.verdict == "UNDETERMINED"  # fail closed, not silently exempt


def test_simulation_import_ban():
    for name in ("tats_simulation", "axion", "ecm_simulation"):
        with pytest.raises(ImportError):
            LA.forbid_simulation_import(name)
    LA.forbid_simulation_import("core")  # the safe module is allowed


def test_action_validation_against_legacy_truth():
    core = _core()
    ok = LA.check_step_actions(core, caps=[1.0] * 32, job_types=[0] * 32,
                               hvac=[0, 0, 0, 0], assignment=[1] * 32)
    assert ok.valid
    bad = LA.check_step_actions(core, caps=[0.70] * 32, job_types=[0] * 32,
                                hvac=[0, 0, 0, 9], assignment=[1] * 31)
    assert not bad.valid
    fields = {v["field"] for v in bad.violations}
    assert {"caps", "hvac", "assignment"} <= fields


def test_conservation_adapter():
    rep = LA.check_step_conservation([0, 1, 2], [2, 0, 1])
    assert rep.kind == "conserved-permutation" and rep.conserved
