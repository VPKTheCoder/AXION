"""Testable thermal-network algebra (Phase 2, P2.1/P2.2).

Every function here mirrors a specific legacy code path in ``Scripts/core.py``
(line references in docstrings) with one deliberate difference: the timestep
``dt`` is a parameter instead of the hard-coded ``CFG["DT"]``. This enables
timestep-refinement experiments (P2.2-F) that legacy cannot run.

Fidelity contract: :func:`rk4_step` with ``dt == CFG["DT"]`` must reproduce
legacy ``ThermalPhysics.step`` to legacy float32 output rounding (~1e-6 at
operating temperatures) on cooling-free, clip-free trajectories. ``tests/test_physics_equations.py::test_replica_matches_legacy``
pins this; if it ever fails, refinement results are meaningless.

Nothing here modifies legacy behavior. Units: SI throughout
(W, J, s, K/°C differences, K/W, J/K). See ``DIMENSIONAL_ANALYSIS.md``.
"""

from __future__ import annotations

import numpy as np

UNITS: dict[str, str] = {
    "T": "degC (state; differences in K)",
    "P_eff": "W",
    "T_in": "degC",
    "R_amb": "K/W",
    "R_mat": "K/W",
    "C": "J/K",
    "dTdt": "K/s",
    "dt": "s",
    "Q": "W",
    "E": "J",
}


def rack_inlet(P_eff: np.ndarray, hvac: np.ndarray | None, *, n_racks: int,
               nodes_per_rack: int, t_ambient: float, k_bypass: float,
               hvac_deg_per_level: float) -> np.ndarray:
    """Per-node inlet temperature. Mirrors ``core.py:108-116`` exactly.

    EQ-INLET: ``T_in[rack] = T_amb + K_bypass * sum(P_eff[rack]) - HVAC_DEG * hvac[rack]``.
    """
    t_in = np.full(P_eff.shape[0], t_ambient, dtype=np.float64)
    for rack in range(n_racks):
        lo, hi = rack * nodes_per_rack, (rack + 1) * nodes_per_rack
        q = float(np.sum(P_eff[lo:hi]))
        level = float(hvac[rack]) if hvac is not None else 0.0
        t_in[lo:hi] = t_ambient + k_bypass * q - hvac_deg_per_level * level
    return t_in


def dTdt(T: np.ndarray, P_eff: np.ndarray, T_in: np.ndarray, R_mat: np.ndarray,
         *, r_amb: float, c_th: float) -> np.ndarray:
    """State derivative. Mirrors ``core.py:118-121`` exactly.

    EQ-ODE: ``C dT_i/dt = P_i - (T_i - T_in,i)/R_amb - sum_j (T_i - T_j)/R_ij``.
    Diagonal of ``R_mat`` must be +inf (self-coupling excluded), mirroring
    ``core.py:77`` (``np.fill_diagonal(R, np.inf)``).
    """
    q_amb = (T - T_in) / r_amb
    with np.errstate(invalid="raise"):
        q_inter = np.sum((T[:, None] - T[None, :]) / R_mat, axis=1)
    return (P_eff - q_amb - q_inter) / c_th


def rk4_step(T: np.ndarray, P_eff: np.ndarray, hvac: np.ndarray | None,
             R_mat: np.ndarray, *, dt: float, n_racks: int, nodes_per_rack: int,
             t_ambient: float, k_bypass: float, hvac_deg_per_level: float,
             r_amb: float, c_th: float,
             t_min: float | None = None, t_max: float | None = None) -> np.ndarray:
    """One RK4 step with frozen ``(P_eff, T_in)`` across sub-stages.

    Mirrors ``core.py:133-138``. Legacy clips to ``[T_AMBIENT, 110]``; pass
    ``t_min``/``t_max`` to reproduce clipping, or ``None`` for the unclipped
    algebra (required for clean convergence measurement, P2.2-F).
    Cooling subtraction is deliberately NOT included here: it is an actuator
    policy (``core.py:124-131``), tested separately in ``test_hvac_cooling.py``.
    """
    t_in = rack_inlet(P_eff, hvac, n_racks=n_racks, nodes_per_rack=nodes_per_rack,
                      t_ambient=t_ambient, k_bypass=k_bypass,
                      hvac_deg_per_level=hvac_deg_per_level)
    p = P_eff.astype(np.float64)
    t = T.astype(np.float64)
    k1 = dTdt(t, p, t_in, R_mat, r_amb=r_amb, c_th=c_th)
    k2 = dTdt(t + dt / 2 * k1, p, t_in, R_mat, r_amb=r_amb, c_th=c_th)
    k3 = dTdt(t + dt / 2 * k2, p, t_in, R_mat, r_amb=r_amb, c_th=c_th)
    k4 = dTdt(t + dt * k3, p, t_in, R_mat, r_amb=r_amb, c_th=c_th)
    out = t + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    if t_min is not None or t_max is not None:
        out = np.clip(out, t_min if t_min is not None else -np.inf,
                      t_max if t_max is not None else np.inf)
    return out
