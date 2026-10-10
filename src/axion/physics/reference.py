"""Independent analytical references (Phase 2, P2.2).

Nothing here re-runs the legacy integrator. Each function derives expected
behavior from the mathematical specification:

* :func:`rc_step_response` — exact scalar solution of a first-order RC node.
* :func:`coupled_equilibrium` — exact steady state of the coupled network for
  fixed power/inlet, by solving the linear system directly (independent method).
* :func:`solve_ivp_reference` — high-accuracy numerical reference (DOP853,
  tight tolerances) for the full network ODE with frozen inputs.
"""

from __future__ import annotations

import numpy as np


def rc_step_response(T0: float, P: float, T_in: float, *, r_amb: float,
                     c_th: float, t: np.ndarray) -> np.ndarray:
    """Exact response of ``C dT/dt = P - (T - T_in)/R`` from ``T(0) = T0``.

    ``T(t) = T* + (T0 - T*) exp(-t/tau)`` with ``T* = T_in + P R``,
    ``tau = R C``. Applies to legacy trajectories only when every node stays
    identical (uniform init + uniform power ⇒ coupling identically zero) and
    no cooling/clipping intervenes.
    """
    tau = r_amb * c_th
    star = T_in + P * r_amb
    return star + (T0 - star) * np.exp(-np.asarray(t, dtype=np.float64) / tau)


def rc_equilibrium(P: float, T_in: float, *, r_amb: float) -> float:
    """Steady state of the scalar node: ``T* = T_in + P R_amb``."""
    return T_in + P * r_amb


def coupled_equilibrium(P_eff: np.ndarray, T_in: np.ndarray, R_mat: np.ndarray,
                        *, r_amb: float) -> np.ndarray:
    """Exact network steady state by direct linear solve (independent method).

    Steady state of EQ-ODE with fixed ``(P_eff, T_in)`` satisfies
    ``A T = b`` with ``A_ii = 1/R_amb + sum_j 1/R_ij``, ``A_ij = -1/R_ij``
    (``1/inf = 0`` on the diagonal), ``b_i = P_i + T_in,i / R_amb``.
    No time-stepping involved — an algebraically independent path to the same
    fixed point the integrator must approach.
    """
    inv = np.where(np.isfinite(R_mat), 1.0 / R_mat, 0.0)
    row_sum = inv.sum(axis=1)
    n = P_eff.shape[0]
    A = np.diag(1.0 / r_amb + row_sum) - inv
    b = P_eff.astype(np.float64) + T_in.astype(np.float64) / r_amb
    return np.linalg.solve(A, b)


def solve_ivp_reference(T0: np.ndarray, P_eff: np.ndarray, T_in: np.ndarray,
                        R_mat: np.ndarray, *, r_amb: float, c_th: float,
                        t_end: float, n_points: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """High-accuracy reference trajectory (DOP853, rtol/atol=1e-11/1e-13).

    Integrates the same EQ-ODE with frozen inputs; used as the smooth-regime
    reference for timestep-refinement measurement (P2.2-F).
    """
    from scipy.integrate import solve_ivp

    t0 = T0.astype(np.float64)
    p = P_eff.astype(np.float64)
    tin = T_in.astype(np.float64)

    def rhs(_t: float, y: np.ndarray) -> np.ndarray:
        return (p - (y - tin) / r_amb
                - np.sum((y[:, None] - y[None, :]) / R_mat, axis=1)) / c_th

    times = np.linspace(0.0, t_end, n_points)
    sol = solve_ivp(rhs, (0.0, t_end), t0, method="DOP853",
                    t_eval=times, rtol=1e-11, atol=1e-13)
    if not sol.success:
        raise RuntimeError(f"solve_ivp reference failed: {sol.message}")
    return times, sol.y.T
