"""Analytical thermal verification tests (P2.2, Tests A–F).

Each test drives the legacy integrator (or the fidelity-pinned replica where
legacy's fixed DT cannot go) against an independently derived expectation.
Tolerances are derived in comments from analytic envelopes, method order, and
float32 output rounding — never tuned to the implementation.
"""

import numpy as np

from axion.physics import battery as BAT


def test_A_zero_input_equilibrium():
    rep = BAT.exp_zero_equilibrium()
    assert rep["pass"], rep
    assert rep["cooling_events"] == 0
    # Bound is the analytic envelope |T0-Tamb| exp(-t/tau) + float slack.
    assert rep["final_max_abs_err_C"] <= rep["analytic_bound_C"]


def test_B_constant_power_rc_response():
    rep = BAT.exp_rc_response()
    assert rep["pass"], rep
    # RK4 truncation at h/tau~0.08 is ~1e-9; the 5e-5 bound is float32
    # output rounding (~1e-6 at 60 °C) with an order of headroom.
    assert rep["max_abs_err_C"] < 5e-5
    assert rep["rms_err_C"] < rep["max_abs_err_C"]
    assert rep["cooling_events"] == 0


def test_C_coupled_equilibrium_matches_direct_solve():
    rep = BAT.exp_coupled_equilibrium()
    assert rep["pass"], rep
    assert rep["target_max_C"] < 65.0  # cooling-free by construction
    assert rep["replica_max_abs_err_C"] < 1e-6
    assert rep["legacy_max_abs_err_C"] < 0.02
    assert rep["cooling_events"] == 0


def test_D_boundary_conditions():
    rep = BAT.exp_boundaries()
    assert rep["pass"], rep
    assert rep["ceiling_value_C"] <= 110.0
    assert rep["floor_value_C"] >= 24.0


def test_E_cooling_response_and_edge_counting():
    rep = BAT.exp_cooling_response()
    assert rep["pass"], rep
    # Net-negative applied power is specified behavior (P - P_COOL), not a bug
    # fix in this phase: pin it so any future change is deliberate.
    assert rep["hot_low_power_p_actual_W"] == 40.0 - 280.0
    assert rep["device_energy_J"] == rep["device_energy_expected_J"]
    assert rep["sustained_counts_once"]


def test_F_refinement_fourth_order():
    rep = BAT.exp_refinement()
    assert rep["pass"], rep
    orders = rep["observed_orders"]
    assert len(orders) == 3
    for order in orders:
        # Theoretical RK4 order is 4 on smooth problems; the [3.5, 4.5] band
        # allows float-rounding wobble at the finest level.
        assert 3.5 <= order <= 4.5
    assert rep["finest_vs_dop853_C"] < 1e-6
    # Errors must shrink monotonically under refinement.
    maxes = [row["max_abs_err_C"] for row in rep["rows"]]
    assert all(b < a for a, b in zip(maxes, maxes[1:]))
