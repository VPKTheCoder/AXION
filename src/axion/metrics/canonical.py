"""Canonical scientific metrics (Phase 2, P2.5) — the single authority for Phase 3.

Design rules (all pinned by synthetic ground-truth tests):

* Every metric carries documented units, denominators, and missing-value
  behavior (``None`` = not computable, never silently 0).
* Work reduction cannot masquerade as improvement: retention denominators are
  *offered* work; substitutions are never completions; SLO compliance states
  its scope and denominator, and unresolved-SLO units are reported separately.
* Thermal risk separates peak change from cumulative exposure (dose).
* Cooling proxies are labeled as proxies: a 100% modeled-water reduction
  reports the baseline value, unit, and proxy status — never a real-world saving.
* The layer is controller-agnostic and trajectory-only: it never alters state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

UNITS: dict[str, str] = {
    "temperature": "degC",
    "time": "s",
    "dose": "degC*s",
    "energy": "J",
    "water": "L",
    "power": "W",
    "count": "work units or events (see denominator)",
    "rate": "fraction in [0, 1] with stated denominator",
    "percent": "percent with stated baseline (None when baseline is zero)",
}


@dataclass
class ThermalRisk:
    """Thermal-risk summary of a recorded node-temperature trajectory."""

    n_nodes: int
    n_steps: int
    dt_s: float
    peak_C: float
    time_weighted_mean_C: float
    threshold_C: float | None = None
    time_above_s: float | None = None
    max_exceedance_C: float | None = None
    dose_Cs: float | None = None
    crossing_count: int | None = None
    event_durations_s: list[float] = field(default_factory=list)


def _as_traj(temps: np.ndarray) -> np.ndarray:
    arr = np.asarray(temps, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError("temps must be a 2-D array [n_steps, n_nodes]")
    if not np.all(np.isfinite(arr)):
        raise ValueError("trajectory contains non-finite values")
    return arr


def thermal_risk(temps: np.ndarray, dt_s: float,
                 threshold_C: float | None = None) -> ThermalRisk:
    """Summarize a temperature trajectory.

    Crossing rule (documented): an up-crossing is a step with
    ``T[t-1] <= threshold < T[t]`` on the node-wise max series. An event runs
    from an up-crossing (inclusive) to the first subsequent step at or below
    threshold; a trailing open event ends at the final step.
    """
    arr = _as_traj(temps)
    n_steps, n_nodes = arr.shape
    peak = float(arr.max())
    mean = float(arr.mean())
    risk = ThermalRisk(n_nodes=n_nodes, n_steps=n_steps, dt_s=float(dt_s),
                       peak_C=peak, time_weighted_mean_C=mean,
                       threshold_C=threshold_C)
    if threshold_C is None:
        return risk
    peak_series = arr.max(axis=1)
    above = peak_series > threshold_C
    risk.time_above_s = float(above.sum()) * dt_s
    risk.max_exceedance_C = float(max(0.0, peak - threshold_C))
    risk.dose_Cs = float(np.sum(np.maximum(0.0, peak_series - threshold_C)) * dt_s)
    crossings = int(np.sum(~above[:-1] & above[1:]))
    if above[0]:
        crossings += 1  # trajectory starts in exceedance: count the open event
    risk.crossing_count = crossings
    durations: list[float] = []
    t = 0
    while t < n_steps:
        if above[t]:
            start = t
            while t < n_steps and above[t]:
                t += 1
            durations.append(float(t - start) * dt_s)
        else:
            t += 1
    risk.event_durations_s = durations
    return risk


@dataclass
class WorkSummary:
    """Useful-work accounting over explicitly recorded work units."""

    offered: int = 0
    completed: int = 0
    rejected: int = 0
    dropped: int = 0
    failed: int = 0
    pending: int = 0
    substituted: int = 0

    @property
    def accounted(self) -> int:
        return self.completed + self.rejected + self.dropped + self.failed + self.pending

    @property
    def retention(self) -> float | None:
        """Completed/offered. None when nothing was offered (no fake 100%)."""
        if self.offered == 0:
            return None
        return self.completed / self.offered


@dataclass
class SLOResult:
    """SLO outcome with explicit denominator and scope."""

    scope: str  # e.g. "inference:L_MAX=19.5ms" or "legacy-tats:all-workloads"
    evaluated: int = 0
    satisfied: int = 0
    violated: int = 0
    unresolved: int = 0
    removed_before_evaluation: int = 0  # work dropped/substituted away: must be reported

    @property
    def compliance(self) -> float | None:
        """Satisfied/evaluated over *decidable* units; None when undecidable."""
        decidable = self.satisfied + self.violated
        if decidable == 0:
            return None
        return self.satisfied / decidable


@dataclass
class CoolingSummary:
    """Cooling/resource summary. Proxies labeled; percents baseline-anchored."""

    cooling_energy_J: float = 0.0
    auxiliary_energy_J: float = 0.0
    water_L: float | None = None  # None when the model path is unsupported
    water_is_proxy: bool = True
    baseline_water_L: float | None = None

    @property
    def water_reduction_pct(self) -> float | None:
        """Percent reduction vs baseline; None when baseline is zero/unknown."""
        if self.water_L is None or self.baseline_water_L is None:
            return None
        if self.baseline_water_L == 0:
            return None
        return 100.0 * (self.baseline_water_L - self.water_L) / self.baseline_water_L


def percent_change(new: float, baseline: float) -> float | None:
    """Percent change vs a baseline; None when the baseline is zero."""
    if baseline == 0:
        return None
    return 100.0 * (new - baseline) / abs(baseline)
