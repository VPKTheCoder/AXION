"""HVAC, inlet-temperature, and cooling-constraint tests (P2.4).

Scope rule: below-ambient inlet is NOT auto-forbidden (a real chiller could do
it) — it is classified by ``guards.inlet_assessment`` against the model's
*declared* scope, which has no refrigeration mechanism. Any future controller
must consult the guard; the tests pin the guard's verdicts on exact cases.
"""

import numpy as np
import pytest

from axion.config.legacy_config import load_core
from axion.physics import equations as EQ
from axion.physics import guards as G
from axion.physics import ledger as L

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CORE = load_core(REPO_ROOT / "Scripts")
CFG = CORE.CFG
N = int(CFG["N_NODES"])
NPR = int(CFG["NODES_PER_RACK"])
NR = int(CFG["N_RACKS"])
T_AMB = float(CFG["T_AMBIENT"])
T_SAFE = float(CFG["T_SAFE"])
K_BP = float(CFG["K_BYPASS"])
HVAC_DEG = float(CFG["HVAC_DEGREE_PER_LEVEL"])
P_COOL = float(CFG["P_COOLING"])
DT = float(CFG["DT"])
R_MAT = CORE._R_MAT.copy()
LEVELS = [int(v) for v in CFG["HVAC_LEVELS"]]


def _inlet(P: np.ndarray, hvac) -> np.ndarray:
    return EQ.rack_inlet(P, hvac, n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                         k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)


def _phys(T0: float):
    phys = CORE.ThermalPhysics(seed=0)
    phys.T = np.full(N, T0, dtype=np.float64)
    phys.cooling_on = np.zeros(N, dtype=bool)
    phys.cooling_events = 0
    phys.cooling_energy_J = 0.0
    return phys


def test_hvac_zero_intermediate_max_exact():
    P = np.full(N, 200.0)
    base = K_BP * 8 * 200.0
    for level, expected in ((0, T_AMB + base), (1, T_AMB + base - 0.5),
                            (2, T_AMB + base - 1.0), (3, T_AMB + base - 1.5)):
        hvac = np.full(NR, level, dtype=np.int32)
        assert np.all(_inlet(P, hvac) == expected)


def test_sub_ambient_without_mechanism_flagged():
    # Zero rack heat + any HVAC>0 drives inlet below ambient (23.5 °C here).
    t_in = _inlet(np.zeros(N), np.ones(NR, dtype=np.int32))
    assert float(t_in[0]) == T_AMB - 0.5
    verdict = G.inlet_assessment(t_in, T_AMB)
    assert verdict.verdict == "sub_ambient_unsupported"
    assert verdict.n_sub_ambient == N
    # Zero authority is physical.
    ok = G.inlet_assessment(_inlet(np.zeros(N), np.zeros(NR, dtype=np.int32)), T_AMB)
    assert ok.verdict == "physical"


def test_ambient_sweep_shifts_margin_linearly():
    t_in = _inlet(np.zeros(N), np.ones(NR, dtype=np.int32))
    for t_amb in (14.0, 24.0, 34.0):
        verdict = G.inlet_assessment(t_amb + (t_in - T_AMB), t_amb)
        assert verdict.verdict == "sub_ambient_unsupported"
        assert verdict.min_margin_K == -0.5


def test_rack_heat_sweep_bypass_slope():
    hvac = np.zeros(NR, dtype=np.int32)
    margins = []
    for watts in (0.0, 1000.0, 2960.0):
        P = np.zeros(N)
        P[0:8] = watts / 8
        margins.append(float(_inlet(P, hvac)[0] - T_AMB))
    assert margins[0] == 0.0
    # Approximate: (T_amb + dq) - T_amb suffers binary cancellation.
    assert margins[1] == pytest.approx(K_BP * 1000.0, abs=1e-12)
    assert margins[2] == pytest.approx(K_BP * 2960.0, abs=1e-12)  # max legacy rack heat


def test_coupled_racks_inlet_independent():
    # Rack 0 heat must not leak into rack 1's inlet (per-rack sums by construction).
    P = np.zeros(N)
    P[0:8] = 370.0
    t_in = _inlet(P, np.zeros(NR, dtype=np.int32))
    assert t_in[8] == T_AMB and t_in[0] == T_AMB + K_BP * 8 * 370.0


def test_emergency_activation_and_repeated_transitions():
    phys = _phys(50.0)
    P = np.full(N, 200.0)
    phys.step(P, np.zeros(NR, dtype=np.int32))
    assert not np.any(phys.cooling_on) and phys.cooling_events == 0
    phys.T = np.full(N, 70.0, dtype=np.float64)  # force excursion
    phys.step(P, np.zeros(NR, dtype=np.int32))
    assert np.all(phys.cooling_on) and phys.cooling_events == N
    e1 = phys.cooling_energy_J
    phys.step(P, np.zeros(NR, dtype=np.int32))  # still hot: energy accrues, events don't
    assert phys.cooling_events == N
    assert phys.cooling_energy_J == e1 + P_COOL * N * DT
    phys.T = np.full(N, 50.0, dtype=np.float64)  # recover then re-trip
    phys.step(P, np.zeros(NR, dtype=np.int32))
    assert not np.any(phys.cooling_on)
    phys.T = np.full(N, 70.0, dtype=np.float64)
    phys.step(P, np.zeros(NR, dtype=np.int32))
    assert phys.cooling_events == 2 * N  # second rising edge counted


def test_cooling_cost_is_abstract_control():
    audit = G.cooling_cost_audit(n_hot=N, p_cooling_W=P_COOL, dt_s=DT)
    assert audit.verdict == "abstract-control"
    assert audit.cop_defined is False
    assert audit.device_energy_J == audit.heat_input_reduction_J == P_COOL * N * DT


def test_actuator_bounds():
    assert G.actuator_bounds(np.array([0, 1, 2, 3]), NR, LEVELS) == []
    bad = G.actuator_bounds(np.array([0, 1, 2, 4]), NR, LEVELS)
    assert len(bad) == 1 and "rack 3" in bad[0]
    assert G.actuator_bounds(np.array([0, 1]), NR, LEVELS) != []


def test_discontinuity_step_stays_finite_and_ledger_marks_it():
    # A step straddling a cooling transition: no order demand, but the books
    # must stay finite and explicitly computed (no silent NaN/cheerful zero).
    from axion.physics import battery as BAT  # noqa: F401  (suite cohesion pin)
    T0 = np.full(N, T_SAFE - 0.01)  # just below threshold
    P_eff = np.full(N, 370.0)  # violent heating crosses the edge mid-step
    T1 = EQ.rk4_step(T0, P_eff, np.zeros(NR), R_MAT, dt=DT,
                     n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                     k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG,
                     r_amb=float(CFG["R_AMB"]), c_th=float(CFG["C_THERMAL"]))
    assert np.all(np.isfinite(T1))
    T_in = _inlet(P_eff, np.zeros(NR, dtype=np.int32))
    rep = L.ledger_step(T0=T0, T1_raw=T1, T1=np.clip(T1, T_AMB, 110.0),
                        P_applied=P_eff, T_in=T_in, R_mat=R_MAT,
                        r_amb=float(CFG["R_AMB"]), c_th=float(CFG["C_THERMAL"]), dt=DT)
    assert np.isfinite(rep.residual_J)
