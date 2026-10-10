"""Canonical-metrics ground-truth tests (P2.5): synthetic trajectories with known answers."""

import numpy as np
import pytest

from axion.metrics import canonical as C


def test_peak_and_mean_known():
    traj = np.array([[20.0, 30.0], [40.0, 10.0]])
    risk = C.thermal_risk(traj, dt_s=1.0)
    assert risk.peak_C == 40.0
    assert risk.time_weighted_mean_C == 25.0
    assert risk.threshold_C is None and risk.dose_Cs is None


def test_dose_crossings_durations_known():
    # Peak series: 60, 66, 67, 61, 59, 70, 70, 58 (threshold 65).
    series = [60, 66, 67, 61, 59, 70, 70, 58]
    traj = np.array([[v, v - 5.0] for v in series])
    risk = C.thermal_risk(traj, dt_s=2.0, threshold_C=65.0)
    assert risk.time_above_s == 4 * 2.0
    assert risk.max_exceedance_C == 5.0
    assert risk.dose_Cs == (1 + 2 + 5 + 5) * 2.0
    assert risk.crossing_count == 2
    assert risk.event_durations_s == [4.0, 4.0]


def test_no_crossings_and_open_start():
    traj = np.full((5, 2), 20.0)
    risk = C.thermal_risk(traj, dt_s=1.0, threshold_C=65.0)
    assert risk.crossing_count == 0 and risk.dose_Cs == 0.0
    assert risk.event_durations_s == [] and risk.time_above_s == 0.0
    hot = np.full((3, 1), 70.0)
    risk = C.thermal_risk(hot, dt_s=1.0, threshold_C=65.0)
    assert risk.crossing_count == 1  # starts in exceedance: open event counted
    assert risk.event_durations_s == [3.0]


def test_non_finite_trajectory_rejected():
    with pytest.raises(ValueError):
        C.thermal_risk(np.array([[20.0, np.nan]]), dt_s=1.0)


def test_work_retention_and_zero_offered():
    w = C.WorkSummary(offered=100, completed=90, dropped=10)
    assert w.retention == 0.9 and w.accounted == 100
    assert C.WorkSummary().retention is None  # no fake 100% on empty denominator


def test_substitution_not_completion():
    # 10 units substituted away: retention counts only true completions.
    w = C.WorkSummary(offered=100, completed=80, substituted=10, pending=10)
    assert w.retention == 0.8


def test_slo_denominator_scope_and_unresolved():
    r = C.SLOResult(scope="inference:L_MAX=19.5ms", evaluated=100,
                    satisfied=90, violated=5, unresolved=5)
    assert r.compliance == 90 / 95  # decidable denominator only
    assert C.SLOResult(scope="x", unresolved=10).compliance is None
    removed = C.SLOResult(scope="x", evaluated=50, satisfied=50,
                          removed_before_evaluation=50)
    assert removed.compliance == 1.0  # value valid, but removal reported alongside


def test_cooling_proxy_and_zero_baseline():
    c = C.CoolingSummary(cooling_energy_J=1120.0, water_L=0.00062,
                         baseline_water_L=0.050864)
    assert c.water_reduction_pct == pytest.approx(98.78, abs=0.01)
    assert c.water_is_proxy is True
    assert C.CoolingSummary(water_L=0.0, baseline_water_L=0.0).water_reduction_pct is None
    assert C.CoolingSummary(water_L=None).water_reduction_pct is None


def test_percent_change_zero_baseline():
    assert C.percent_change(5.0, 0.0) is None
    assert C.percent_change(90.0, 100.0) == -10.0
