"""Action validation: caps, HVAC, permutations, coverage, numerics (P1.4)."""

import numpy as np

from axion.constraints import actions as A

ALLOWED = [[1.0, 0.85], [1.0], [], [1.0, 0.85, 0.7, 0.55, 0.4]]


def test_valid_caps():
    rep = A.validate_caps([1.0, 1.0, 0.7], [0, 1, 3], ALLOWED)
    assert rep.valid


def test_invalid_cap_and_empty_allowed_set():
    rep = A.validate_caps([0.70], [0], ALLOWED)  # 0.70 not allowed for GEMM
    assert not rep.valid and rep.violations[0]["field"] == "caps"
    rep = A.validate_caps([1.0], [2], ALLOWED)  # empty allowed set: nothing legal
    assert not rep.valid


def test_unknown_workload_and_length_mismatch():
    assert not A.validate_caps([1.0], [9], ALLOWED).valid
    assert not A.validate_caps([1.0, 1.0], [0], ALLOWED).valid
    assert not A.validate_caps([float("nan")], [0], ALLOWED).valid


def test_hvac_bounds():
    assert A.validate_hvac([0, 3], 2, [0, 1, 2, 3]).valid
    bad = A.validate_hvac([0, 4], 2, [0, 1, 2, 3])
    assert not bad.valid
    assert not A.validate_hvac([0], 2, [0, 1, 2, 3]).valid
    assert not A.validate_hvac([0, True], 2, [0, 1, 2, 3]).valid


def test_permutation_bijection():
    assert A.validate_permutation([2, 0, 1], 3).valid
    dup = A.validate_permutation([1, 1, 2], 3)
    assert not dup.valid and dup.violations[0]["reason"] == "not-a-bijection"
    assert not A.validate_permutation([0, 1], 3).valid


def test_assignment_coverage():
    assert A.validate_assignment_coverage([0, 3, 1], 3, 4).valid
    bad = A.validate_assignment_coverage([0, 4, 1], 3, 4)
    assert not bad.valid
    assert not A.validate_assignment_coverage([0, 1], 3, 4).valid


def test_finite_vector():
    assert A.validate_finite_vector([20.0, 30.5], "T").valid
    rep = A.validate_finite_vector([20.0, float("nan"), float("inf")], "T")
    assert len(rep.violations) == 2


def test_numpy_integers_accepted_bool_rejected():
    # Phase 2 regression: legacy passes int32 arrays; np integers are Integral
    # but must not be rejected, while bool must never validate as a level.
    assert A.validate_hvac(np.array([0, 3], dtype=np.int32), 2, [0, 1, 2, 3]).valid
    assert A.validate_permutation(np.array([1, 0], dtype=np.int64), 2).valid
    assert A.validate_assignment_coverage(np.array([0, 3]), 2, 4).valid
    assert not A.validate_hvac([0, True], 2, [0, 1, 2, 3]).valid
