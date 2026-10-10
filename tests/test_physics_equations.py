"""Core-equation unit tests (P2.1): mirror fidelity, units, algebraic properties.

Fidelity strategy: the replica in ``physics/equations.py`` is pinned
bit-near-exact to legacy ``ThermalPhysics`` at ``dt == CFG["DT"]`` on
cooling-free, clip-free trajectories (``test_replica_matches_legacy``). All
refinement claims (P2.2-F) rest on that pin.
"""

import numpy as np
import pytest

from axion.config.legacy_config import load_core
from axion.physics import equations as EQ

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CORE = load_core(REPO_ROOT / "Scripts")

CFG = CORE.CFG
N = int(CFG["N_NODES"])
NPR = int(CFG["NODES_PER_RACK"])
NR = int(CFG["N_RACKS"])
R_AMB = float(CFG["R_AMB"])
C_TH = float(CFG["C_THERMAL"])
T_AMB = float(CFG["T_AMBIENT"])
K_BP = float(CFG["K_BYPASS"])
HVAC_DEG = float(CFG["HVAC_DEGREE_PER_LEVEL"])
DT = float(CFG["DT"])
R_MAT = CORE._R_MAT.copy()


def _phys_kwargs() -> dict:
    return dict(n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG,
                r_amb=R_AMB, c_th=C_TH)


def _uniform_phys(power: float, t0: float):
    phys = CORE.ThermalPhysics(seed=0)
    phys.T = np.full(N, t0, dtype=np.float64)
    phys.cooling_on = np.zeros(N, dtype=bool)
    return phys


def test_replica_matches_legacy():
    """Replica RK4 == legacy step at dt=DT (cooling-free, clip-free)."""
    phys = _uniform_phys(210.0, 50.0)
    P = np.full(N, 210.0)
    hvac = np.zeros(NR, dtype=np.int32)
    T_legacy, _ = phys.step(P, hvac)
    T_replica = EQ.rk4_step(np.full(N, 50.0), P, hvac, R_MAT, dt=DT,
                            **_phys_kwargs())
    # Legacy returns float32 (core.py:139); replica is float64. The bound is the
    # float32 rounding of ~60 °C magnitudes, not an algebraic difference.
    assert np.max(np.abs(T_legacy.astype(np.float64) - T_replica)) < 5e-6


def test_replica_matches_legacy_nonuniform():
    """Fidelity also holds off-symmetry (deterministic varied power)."""
    rng = np.random.default_rng(0)
    T0 = rng.uniform(30.0, 55.0, N)
    P = rng.uniform(40.0, 370.0, N)
    phys = _uniform_phys(0.0, 0.0)
    phys.T = T0.copy()
    hvac = np.array([0, 1, 2, 3], dtype=np.int32)
    T_legacy, _ = phys.step(P, hvac)
    T_replica = EQ.rk4_step(T0, P, hvac, R_MAT, dt=DT, **_phys_kwargs())
    assert np.max(np.abs(T_legacy.astype(np.float64) - T_replica)) < 5e-6


def test_inlet_matches_legacy():
    phys = _uniform_phys(0.0, 0.0)
    P = np.arange(N, dtype=np.float64) * 10.0
    hvac = np.array([3, 2, 1, 0], dtype=np.int32)
    assert np.allclose(
        EQ.rack_inlet(P, hvac, **{k: v for k, v in _phys_kwargs().items()
                                  if k in ("n_racks", "nodes_per_rack", "t_ambient",
                                           "k_bypass", "hvac_deg_per_level")}),
        phys.rack_inlet(P, hvac))


def test_units_tau_is_seconds():
    """R_amb [K/W] * C [J/K] = [s]; effective tau must be positive seconds."""
    tau = R_AMB * C_TH
    assert tau == pytest.approx(13.05, abs=0.01)
    assert set(EQ.UNITS[k] for k in ("R_amb", "C", "dt")) == {"K/W", "J/K", "s"}


def test_dTdt_zero_at_uniform_equilibrium():
    """At T == T_in + P*R_amb uniformly, coupling vanishes and dTdt == 0."""
    P = 210.0
    T_star = T_AMB + K_BP * 8 * P + P * R_AMB
    T = np.full(N, T_star)
    T_in = EQ.rack_inlet(np.full(N, P), None, n_racks=NR, nodes_per_rack=NPR,
                         t_ambient=T_AMB, k_bypass=K_BP,
                         hvac_deg_per_level=HVAC_DEG)
    d = EQ.dTdt(T, np.full(N, P), T_in, R_MAT, r_amb=R_AMB, c_th=C_TH)
    assert np.max(np.abs(d)) < 1e-9


def test_coupling_antisymmetric():
    """Internal exchange summed over the network is zero for arbitrary T."""
    rng = np.random.default_rng(1)
    T = rng.uniform(20.0, 80.0, N)
    with np.errstate(divide="ignore", invalid="ignore"):
        pair = (T[:, None] - T[None, :]) / R_MAT
    pair[~np.isfinite(pair)] = 0.0
    assert abs(float(np.sum(pair))) < 1e-6


def test_inlet_linear_in_rack_power():
    """EQ-INLET is affine in rack power with slope K_bypass [K/W]."""
    P0 = np.zeros(N)
    P1 = np.zeros(N)
    P1[0:8] = 100.0
    t0 = EQ.rack_inlet(P0, None, n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                       k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)
    t1 = EQ.rack_inlet(P1, None, n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                       k_bypass=K_BP, hvac_deg_per_level=HVAC_DEG)
    assert t1[0] - t0[0] == pytest.approx(K_BP * 800.0)
    assert np.all(t1[8:] == t0[8:])  # other racks unaffected
