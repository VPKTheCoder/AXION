"""HVAC / cooling guardrails for future controllers (Phase 2, P2.4).

These functions change no legacy behavior. They answer the audit's question —
"can the controller exploit an unsupported temperature effect?" — at runtime:

* :func:`inlet_assessment` classifies a computed inlet field as ``physical``,
  ``sub_ambient_unsupported`` (below ambient with no refrigeration mechanism
  in the model), or ``invalid`` (non-finite).
* :func:`cooling_cost_audit` checks the emergency-cooling cost relationship:
  the model charges device energy ``P_COOLING`` per hot node with no COP, so
  the "benefit per cost" has no physical meaning — reported as an abstract
  control, never a calibrated tradeoff.
* :func:`actuator_bounds` validates HVAC/cap vectors against the legacy config.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass, field

import numpy as np


@dataclass
class InletAssessment:
    """Verdict on one inlet-temperature field."""

    verdict: str  # "physical" | "sub_ambient_unsupported" | "invalid"
    n_sub_ambient: int = 0
    min_margin_K: float = 0.0  # min(T_in - T_amb); negative when sub-ambient
    detail: str = ""


@dataclass
class CoolingCostAudit:
    """Cost/benefit audit of one emergency-cooling step."""

    n_hot: int = 0
    device_energy_J: float = 0.0
    heat_input_reduction_J: float = 0.0  # == device energy by construction (L2)
    cop_defined: bool = False
    verdict: str = "abstract-control"
    notes: list[str] = field(default_factory=list)


def inlet_assessment(T_in: np.ndarray, t_ambient: float,
                     refrigeration_modeled: bool = False) -> InletAssessment:
    """Classify an inlet field given the model's declared scope.

    Legacy scope has no refrigeration cycle, so any ``T_in < T_amb`` is
    ``sub_ambient_unsupported`` (usable by the optimizer only if explicitly
    allowed by a future scope change). Set ``refrigeration_modeled=True`` only
    when a validated chiller model exists.
    """
    tin = np.asarray(T_in, dtype=np.float64)
    if not np.all(np.isfinite(tin)):
        return InletAssessment("invalid", detail="non-finite inlet values")
    margin = float(np.min(tin - t_ambient))
    n_sub = int(np.sum(tin < t_ambient))
    if n_sub and not refrigeration_modeled:
        return InletAssessment(
            "sub_ambient_unsupported", n_sub_ambient=n_sub, min_margin_K=margin,
            detail=(f"{n_sub} nodes with inlet below ambient (min margin "
                    f"{margin:+.3f} K) and no refrigeration mechanism modeled"))
    return InletAssessment("physical", n_sub_ambient=0, min_margin_K=margin,
                           detail="inlet at or above ambient")


def cooling_cost_audit(*, n_hot: int, p_cooling_W: float, dt_s: float) -> CoolingCostAudit:
    """Audit the emergency-cooling cost relationship for one step."""
    device = float(p_cooling_W) * int(n_hot) * float(dt_s)
    return CoolingCostAudit(
        n_hot=int(n_hot), device_energy_J=device,
        heat_input_reduction_J=device, cop_defined=False,
        verdict="abstract-control",
        notes=["Model charges device energy with no COP; heat-input reduction "
               "equals device energy by algebraic construction (ledger L2), not "
               "by thermodynamics. Treat as abstract control."])


def actuator_bounds(hvac: np.ndarray, n_racks: int,
                    levels: list[int]) -> list[str]:
    """Validate HVAC actuator vector; return violation strings (empty = valid)."""
    problems: list[str] = []
    if len(hvac) != n_racks:
        problems.append(f"hvac length {len(hvac)} != n_racks {n_racks}")
        return problems
    allowed = set(int(v) for v in levels)
    for rack, level in enumerate(hvac):
        # numbers.Integral covers numpy integers (legacy passes int32 arrays);
        # bool remains excluded (True == 1 must not validate as a level).
        if (isinstance(level, bool) or not isinstance(level, numbers.Integral)
                or int(level) not in allowed):
            problems.append(f"rack {rack}: level {level!r} not in {sorted(allowed)}")
    return problems
