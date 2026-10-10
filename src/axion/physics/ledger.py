"""Independent energy-accounting ledger (Phase 2, P2.3).

Convention (documented, sign-explicit): for one step taking state ``T0 -> T1``
over ``dt`` under the *specified* legacy algebra with applied heat input
``P_applied`` (i.e. AFTER the cooling subtraction — see limitation L2 below):

* ``dU = C * sum(T1 - T0)`` — change in stored thermal energy [J].
* ``E_in = sum(P_applied) * dt`` — modeled heat input [J].
* ``E_amb = sum((T - T_in)/R_amb) * dt`` — boundary loss, evaluated on the
  same RK stages as the integrator where practical; the step-level ledger
  below uses the trapezoidal average of the endpoint fluxes, and the
  residual therefore also absorbs quadrature error (bounded and tested).
* ``E_inter = 0`` identically — internal exchanges are antisymmetric; the
  ledger *verifies* this instead of assuming it (``internal_exchange_net``).
* ``residual = dU - (E_in - E_amb)`` — must vanish to integrator/quadrature
  accuracy on clip-free, actuator-constant steps.

Limitation L1 (clipping): legacy clips state to ``[T_AMBIENT, 110]`` after the
RK update. Clipping destroys/adds modeled energy; the ledger reports
``clip_energy = C * sum(T1_clipped - T1_raw)`` separately and marks the step.
Limitation L2 (cooling): legacy subtracts ``P_COOLING`` from the heat input of
hot nodes. The ledger treats this exactly as the equations do — reduced heat
input — and separately records ``cooling_device_energy = P_COOLING*n_hot*dt``.
The model establishes NO relationship between device electrical energy and
heat removed (no COP); the ledger never equates them (see ENERGY report).
Limitation L3 (water): ``W = E_device/(eta*L_v)`` is an empirical proxy with
its own ledger entry; it is not derived from the thermal ODE.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class LedgerStep:
    """All ledger quantities for one step, SI units (J, W, s, °C)."""

    dU_J: float = 0.0
    E_in_J: float = 0.0
    E_amb_J: float = 0.0
    E_inter_net_W: float = 0.0  # instantaneous net internal exchange (must be ~0)
    cooling_device_J: float = 0.0
    clip_energy_J: float = 0.0
    clipped: bool = False
    residual_J: float = 0.0
    notes: list[str] = field(default_factory=list)


def internal_exchange_net(T: np.ndarray, R_mat: np.ndarray) -> float:
    """Net internal exchange ``sum_i sum_j (T_i - T_j)/R_ij`` [W].

    Antisymmetric ⇒ identically zero for any finite coupling matrix
    (diagonal +inf contributes 0). Computed, not assumed.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        pair = (T[:, None] - T[None, :]) / R_mat
    pair[~np.isfinite(pair)] = 0.0
    return float(np.sum(pair))


def ledger_step(*, T0: np.ndarray, T1_raw: np.ndarray, T1: np.ndarray,
                P_applied: np.ndarray, T_in: np.ndarray, R_mat: np.ndarray,
                r_amb: float, c_th: float, dt: float,
                cooling_device_J: float = 0.0) -> LedgerStep:
    """Close the books for one step of the *specified* algebra.

    ``T1_raw`` is the pre-clip state, ``T1`` the post-clip state; pass
    ``T1_raw is T1`` (same values) when no clip model applies.
    """
    t0 = T0.astype(np.float64)
    t1 = T1.astype(np.float64)
    traw = T1_raw.astype(np.float64)
    p = P_applied.astype(np.float64)
    tin = T_in.astype(np.float64)

    dU = c_th * float(np.sum(t1 - t0))
    e_in = float(np.sum(p)) * dt
    flux0 = (t0 - tin) / r_amb
    flux1 = (t1 - tin) / r_amb
    e_amb = float(np.sum(0.5 * (flux0 + flux1))) * dt
    e_inter = internal_exchange_net(t0, R_mat)
    clip_e = c_th * float(np.sum(t1 - traw))
    clipped = bool(np.any(t1 != traw))
    residual = dU - (e_in - e_amb)
    notes: list[str] = []
    if clipped:
        notes.append("clip altered state; clip_energy reported separately")
    return LedgerStep(dU_J=dU, E_in_J=e_in, E_amb_J=e_amb,
                      E_inter_net_W=e_inter, cooling_device_J=cooling_device_J,
                      clip_energy_J=clip_e, clipped=clipped,
                      residual_J=residual, notes=notes)


def relative_residual(residual_J: float, scale_J: float) -> float | None:
    """Scale-aware relative residual; ``None`` when the scale is ~zero.

    Near-zero denominators return ``None`` instead of a meaningless ratio —
    callers must handle energy-quiet steps explicitly.
    """
    if abs(scale_J) < 1e-9:
        return None
    return residual_J / abs(scale_J)
