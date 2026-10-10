"""Work accounting: permutation vs substitution + job ledger (P1.4, C-01)."""

import pytest

from axion.constraints.workload_accounting import (
    WorkLedger,
    LedgerError,
    OfferedJob,
    check_conservation,
    classify_step,
)


def test_identity_conserved():
    rep = classify_step([0, 1, 2, 5], [0, 1, 2, 5])
    assert rep.kind == "conserved-identity" and rep.conserved
    assert rep.substitutions == []


def test_permutation_conserved_with_reroute_record():
    rep = check_conservation([0, 1, 2], [2, 0, 1])
    assert rep.kind == "conserved-permutation" and rep.conserved
    # Rerouted nodes are listed but the multiset is intact.
    assert {s["node"] for s in rep.substitutions} == {0, 1, 2}


def test_substitution_detected_and_explicit():
    # Legacy TATS fallback shape: hot GEMM (0) overwritten by Embed (4).
    rep = classify_step([0, 0, 1, 2], [4, 0, 1, 2])
    assert rep.kind == "substitution" and not rep.conserved
    assert rep.substitutions == [{"node": 0, "offered": 0, "assigned": 4}]


def test_truncated_lengths():
    rep = classify_step([0, 1], [0])
    assert rep.kind == "truncated" and not rep.conserved


def test_ledger_happy_path():
    ledger = WorkLedger()
    ledger.offer(OfferedJob("j1", 0))
    ledger.offer(OfferedJob("j2", 5))
    ledger.assign("j1", 2)  # reroute to another workload is assignment, not loss
    ledger.assign("j2", 5)
    ledger.finish("j1", "completed")
    ledger.finish("j2", "completed")
    audit = ledger.audit()
    assert audit["complete"] and audit["missing_terminal"] == []


def test_ledger_substitution_never_completed():
    ledger = WorkLedger()
    ledger.offer(OfferedJob("j1", 0))
    ledger.substitute("j1", 4)
    with pytest.raises(LedgerError):
        ledger.finish("j1", "completed")  # substitution != completion
    ledger.finish("j1", "dropped")
    audit = ledger.audit()
    assert audit["complete"]
    assert audit["substituted"] == {"j1": 4}


def test_ledger_duplicate_and_disappearance():
    ledger = WorkLedger()
    ledger.offer(OfferedJob("j1", 0))
    with pytest.raises(LedgerError):
        ledger.offer(OfferedJob("j1", 0))  # duplicate offer
    with pytest.raises(LedgerError):
        ledger.assign("ghost", 1)  # unoffered
    audit = ledger.audit()
    assert not audit["complete"]
    assert audit["missing_terminal"] == ["j1"]


def test_ledger_explicit_rejection_accounted():
    ledger = WorkLedger()
    ledger.offer(OfferedJob("j1", 5))
    ledger.finish("j1", "rejected")
    audit = ledger.audit()
    assert audit["complete"]
