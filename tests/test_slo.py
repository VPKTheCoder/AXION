"""SLO semantics: applicable, batch, unresolved, fail-closed (P1.4, D-03)."""

from axion.constraints import slo as S


def _table():
    return S.build_table(
        ["GEMM", "Attn", "Grad"], [14.0, 19.0, 24.0], 19.5,
        slo_bound={0, 1}, unresolved={2})


def test_applicable_pass_and_fail():
    table = _table()
    ok = S.check_step([0, 1], [1.0, 1.0], table)
    assert ok.verdict == "PASS" and S.guarantee(ok)
    bad = S.check_step([1], [0.85], table)  # 19/0.85 = 22.35 > 19.5
    assert bad.verdict == "FAIL" and not S.guarantee(bad)
    assert bad.violations[0]["name"] == "Attn"


def test_batch_workload_unbounded():
    table = S.build_table(["Embed"], [1.0], 19.5, slo_bound=set())
    rep = S.check_step([0], [0.40], table)
    assert rep.verdict == "PASS" and S.guarantee(rep)


def test_unresolved_fails_closed():
    table = _table()
    rep = S.check_step([2], [1.0], table)  # Gradient semantics unresolved
    assert rep.verdict == "UNDETERMINED"
    assert not S.guarantee(rep)  # fail closed: no guarantee without decidability
    assert rep.undetermined and rep.violations == []


def test_mixed_fail_dominates_undetermined():
    table = _table()
    rep = S.check_step([1, 2], [0.85, 1.0], table)
    assert rep.verdict == "FAIL"


def test_length_mismatch_and_unknown_index_fail():
    table = _table()
    assert S.check_step([0, 1], [1.0], table).verdict == "FAIL"
    rep = S.check_step([9], [1.0], table)
    assert rep.verdict == "FAIL"


def test_non_finite_cap_fails():
    table = _table()
    assert S.check_step([0], [float("nan")], table).verdict == "FAIL"
    assert S.check_step([0], [float("inf")], table).verdict == "FAIL"


def test_allows_tri_state():
    table = _table()
    assert table[0].allows(1.0) is True
    assert table[1].allows(0.85) is False
    assert table[2].allows(1.0) is None
