"""Centralized workload/SLO definitions and independent SLO validation.

Phase 0 decisions D-03 / findings C-02, R-04: legacy code gives Gradient
(index 5, 24 ms) an empty allowed-cap set under the 19.5 ms inference SLO,
then resolves the contradiction three different ways (TATS substitutes,
AXION exempts, ECM refuses). This module represents that uncertainty
explicitly instead of inventing a Gradient SLO or silently exempting it:

* ``slo_applies=True``  — workload is SLO-bound (latency threshold enforced).
* ``slo_applies=False`` — workload is batch (no latency threshold).
* ``slo_applies=None``  — UNRESOLVED legacy semantics; any verdict involving
  such a workload is ``UNDETERMINED``, and :func:`guarantee` fails closed.

The validator scores *observed* (assignment, caps) pairs independently of
whichever controller produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LATENCY_METRIC = "L_eff = L_rated / cap <= L_MAX"


@dataclass(frozen=True)
class WorkloadSLO:
    """SLO definition for one workload class."""

    index: int
    name: str
    rated_latency_ms: float
    slo_applies: bool | None  # None = unresolved legacy semantics
    threshold_ms: float | None = None
    reason: str = ""

    def allows(self, cap: float) -> bool | None:
        """True/False when decidable; None when SLO applicability is unresolved."""
        if self.slo_applies is None:
            return None
        if not self.slo_applies:
            return True
        if self.threshold_ms is None:
            return None
        if cap <= 0:
            return False
        return (self.rated_latency_ms / cap) <= self.threshold_ms + 1e-9


@dataclass
class SLOReport:
    """Outcome of scoring one observed step."""

    verdict: str  # "PASS" | "FAIL" | "UNDETERMINED"
    violations: list[dict[str, object]] = field(default_factory=list)
    undetermined: list[dict[str, object]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"


def build_table(
    names: list[str],
    rated_latency_ms: list[float],
    threshold_ms: float,
    slo_bound: list[bool] | set[int] | None = None,
    unresolved: set[int] | None = None,
) -> list[WorkloadSLO]:
    """Build an explicit SLO table.

    ``slo_bound`` as a set of indices marks bound workloads (legacy
    ``SLO_SENSITIVE`` shape); as a list it must cover every workload.
    ``unresolved`` marks indices whose applicability is genuinely unknown
    (takes precedence over ``slo_bound``).
    """
    unresolved = set(unresolved or set())
    table: list[WorkloadSLO] = []
    for i, (name, lat) in enumerate(zip(names, rated_latency_ms)):
        if i in unresolved:
            table.append(WorkloadSLO(i, name, float(lat), None, None,
                                     reason="unresolved legacy semantics"))
            continue
        if isinstance(slo_bound, set):
            applies: bool | None = i in slo_bound
        elif slo_bound is None:
            applies = True
        else:
            applies = bool(slo_bound[i])
        table.append(WorkloadSLO(
            i, name, float(lat), applies,
            threshold_ms if applies else None,
            reason="batch workload (no latency threshold)" if not applies
            else f"inference SLO via {LATENCY_METRIC}",
        ))
    return table


def check_step(
    assignment: list[int],
    caps: list[float],
    table: list[WorkloadSLO],
) -> SLOReport:
    """Score one observed (assignment, caps) step.

    *FAIL* if any decidable workload violates its threshold; *UNDETERMINED*
    if nothing decidable fails but at least one workload's applicability is
    unresolved; *PASS* otherwise. Length mismatch is a FAIL (unscoreable step
    cannot pass a guarantee).
    """
    if len(assignment) != len(caps):
        return SLOReport("FAIL", violations=[{
            "reason": "assignment/caps length mismatch",
            "n_assignment": len(assignment), "n_caps": len(caps)}])
    by_index = {w.index: w for w in table}
    report = SLOReport("PASS")
    for node, (w, cap) in enumerate(zip(assignment, caps)):
        spec = by_index.get(int(w))
        if spec is None:
            report.verdict = "FAIL"
            report.violations.append({"node": node, "workload": int(w),
                                      "reason": "unknown workload index"})
            continue
        if not isinstance(cap, (int, float)) or cap != cap or cap in (float("inf"), float("-inf")):
            report.verdict = "FAIL"
            report.violations.append({"node": node, "workload": int(w), "cap": cap,
                                      "reason": "non-finite cap"})
            continue
        outcome = spec.allows(float(cap))
        if outcome is None:
            report.undetermined.append({"node": node, "workload": spec.index,
                                        "name": spec.name, "reason": spec.reason})
        elif outcome is False:
            report.verdict = "FAIL"
            report.violations.append({
                "node": node, "workload": spec.index, "name": spec.name,
                "cap": float(cap),
                "L_eff_ms": spec.rated_latency_ms / float(cap) if cap else None,
                "threshold_ms": spec.threshold_ms, "metric": LATENCY_METRIC})
    if report.verdict == "PASS" and report.undetermined:
        report.verdict = "UNDETERMINED"
    return report


def guarantee(report: SLOReport) -> bool:
    """Fail-closed guarantee: True only for an unambiguous PASS."""
    return report.verdict == "PASS"
