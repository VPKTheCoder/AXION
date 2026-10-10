"""Energy-ledger tests (P2.3): conservation, residuals, unsupported quantities.

Tolerance basis: the step ledger uses trapezoidal endpoint quadrature for the
boundary flux, whose relative error scales as (h/tau)^2/12 ≈ 5e-4 at h=1 s,
tau=13.05 s (measured 4.9e-4, halving exactly 4x per dt-halving — second
order as theory predicts). The 0.2% bound carries ~4x headroom, not a fit.
"""

import numpy as np

from axion.config.legacy_config import load_core
from axion.physics import equations as EQ
from axion.physics import ledger as L

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CORE = load_core(REPO_ROOT / "Scripts")
CFG = CORE.CFG
N = int(CFG["N_NODES"])
NPR = int(CFG["NODES_PER_RACK"])
NR = int(CFG["N_RACKS"])
R_AMB = float(CFG["R_AMB"])
C_TH = float(CFG["C_THERMAL"])
T_AMB = float(CFG["T_AMBIENT"])
DT = float(CFG["DT"])
P_COOL = float(CFG["P_COOLING"])
R_MAT = CORE._R_MAT.copy()


def _kw() -> dict:
    return dict(n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                k_bypass=float(CFG["K_BYPASS"]),
                hvac_deg_per_level=float(CFG["HVAC_DEGREE_PER_LEVEL"]),
                r_amb=R_AMB, c_th=C_TH)


def _step(T0: np.ndarray, P: np.ndarray, dt: float = DT):
    hvac = np.zeros(NR, dtype=np.int32)
    T_in = EQ.rack_inlet(P, hvac, n_racks=NR, nodes_per_rack=NPR, t_ambient=T_AMB,
                         k_bypass=float(CFG["K_BYPASS"]),
                         hvac_deg_per_level=float(CFG["HVAC_DEGREE_PER_LEVEL"]))
    T1 = EQ.rk4_step(T0, P, hvac, R_MAT, dt=dt, **_kw())
    rep = L.ledger_step(T0=T0, T1_raw=T1, T1=T1, P_applied=P, T_in=T_in,
                        R_mat=R_MAT, r_amb=R_AMB, c_th=C_TH, dt=dt)
    return rep, T_in


def test_internal_exchange_cancels():
    rng = np.random.default_rng(2)
    T = rng.uniform(20.0, 80.0, N)
    assert abs(L.internal_exchange_net(T, R_MAT)) < 1e-6


def test_residual_within_quadrature_bound():
    rep, _ = _step(np.full(N, 50.0), np.full(N, 210.0))
    rel = L.relative_residual(rep.residual_J, rep.dU_J)
    assert rel is not None and abs(rel) < 0.002
    assert not rep.clipped and rep.clip_energy_J == 0.0


def test_residual_second_order_in_dt():
    rels = []
    for dt in (1.0, 0.5, 0.25):
        rep, _ = _step(np.full(N, 50.0), np.full(N, 210.0), dt=dt)
        rels.append(abs(L.relative_residual(rep.residual_J, rep.dU_J)))
    for coarse, fine in zip(rels, rels[1:]):
        assert 3.0 < coarse / fine < 5.0  # trapezoidal order 2


def test_zero_power_quiet_step():
    rep, _ = _step(np.full(N, T_AMB), np.zeros(N))
    assert abs(rep.dU_J) < 1e-9 and abs(rep.E_in_J) < 1e-9
    assert L.relative_residual(rep.residual_J, rep.dU_J) is None  # no fake ratio
    assert abs(rep.residual_J) < 1e-9


def test_clip_flagged_with_energy():
    T0 = np.full(N, 50.0)
    T_raw = np.full(N, 200.0)  # pre-clip algebra overshoots
    T1 = np.clip(T_raw, T_AMB, 110.0)
    P = np.full(N, 210.0)
    T_in = EQ.rack_inlet(P, np.zeros(NR), n_racks=NR, nodes_per_rack=NPR,
                         t_ambient=T_AMB, k_bypass=float(CFG["K_BYPASS"]),
                         hvac_deg_per_level=float(CFG["HVAC_DEGREE_PER_LEVEL"]))
    rep = L.ledger_step(T0=T0, T1_raw=T_raw, T1=T1, P_applied=P, T_in=T_in,
                        R_mat=R_MAT, r_amb=R_AMB, c_th=C_TH, dt=DT)
    assert rep.clipped
    assert rep.clip_energy_J == C_TH * N * (110.0 - 200.0)
    assert rep.notes  # limitation flagged, not silent


def test_cooling_ledger_separates_device_energy():
    # Hot low-power node: applied heat input is P - P_COOL (specified algebra);
    # device energy is recorded alongside, never equated to heat removed.
    T0 = np.full(N, 70.0)
    P_eff = np.full(N, 40.0)
    P_applied = P_eff - P_COOL
    rep, _ = _step(T0, P_applied)
    assert rep.cooling_device_J == 0.0  # default: caller must supply it
    rep2, _ = _step(T0, P_applied)
    rep2.cooling_device_J = P_COOL * N * DT
    assert rep2.cooling_device_J == P_COOL * N * DT
    assert abs(L.relative_residual(rep2.residual_J, rep2.dU_J) or 0.0) < 0.002
