"""Action validation: caps, HVAC levels, references, numerics, coverage.

Validates *proposed or observed* actions against the actual legacy
configuration (allowed-cap sets, HVAC levels, rack counts) supplied by the
caller — typically :mod:`axion.constraints.legacy_adapter`, which reads them
from ``Scripts/core.py``. Nothing is hard-coded here, so a future config
change cannot silently desynchronize the validator.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass, field
import math


@dataclass
class ActionReport:
    """Collects violations; empty means the action is valid."""

    violations: list[dict[str, object]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.violations

    def add(self, field_name: str, reason: str, **detail: object) -> None:
        entry: dict[str, object] = {"field": field_name, "reason": reason}
        entry.update(detail)
        self.violations.append(entry)


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def validate_caps(
    caps: list[float],
    job_types: list[int],
    allowed_caps: list[list[float]],
    *,
    tol: float = 1e-4,
) -> ActionReport:
    """Each node's cap must be within ``tol`` of an allowed level for its workload."""
    report = ActionReport()
    if len(caps) != len(job_types):
        report.add("caps", "length-mismatch",
                   n_caps=len(caps), n_jobs=len(job_types))
        return report
    for node, (cap, job) in enumerate(zip(caps, job_types)):
        if not _finite(cap):
            report.add("caps", "non-finite-cap", node=node, cap=cap)
            continue
        if not isinstance(job, int) or not 0 <= job < len(allowed_caps):
            report.add("caps", "unknown-workload", node=node, workload=job)
            continue
        if not any(abs(float(cap) - c) <= tol for c in allowed_caps[job]):
            report.add("caps", "cap-not-allowed", node=node,
                       cap=float(cap), workload=int(job),
                       allowed=list(allowed_caps[job]))
    return report


def validate_hvac(hvac: list[int], n_racks: int, levels: list[int]) -> ActionReport:
    """HVAC vector must cover exactly the racks with legal levels."""
    report = ActionReport()
    if len(hvac) != n_racks:
        report.add("hvac", "length-mismatch", n_got=len(hvac), n_racks=n_racks)
        return report
    allowed = set(int(v) for v in levels)
    for rack, level in enumerate(hvac):
        if (isinstance(level, bool) or not isinstance(level, numbers.Integral)
                or int(level) not in allowed):
            report.add("hvac", "level-not-allowed", rack=rack,
                       level=level, allowed=sorted(allowed))
    return report


def validate_permutation(perm: list[int], n: int) -> ActionReport:
    """A node<-job permutation must be a bijection over ``range(n)``."""
    report = ActionReport()
    if len(perm) != n:
        report.add("perm", "length-mismatch", n_got=len(perm), n_expected=n)
        return report
    if any(isinstance(v, bool) or not isinstance(v, numbers.Integral) for v in perm):
        report.add("perm", "non-integer-entry", perm=[str(v) for v in perm])
        return report
    perm = [int(v) for v in perm]
    if sorted(perm) != list(range(n)):
        report.add("perm", "not-a-bijection",
                   missing=sorted(set(range(n)) - set(perm)),
                   duplicated=sorted(v for v in set(perm) if perm.count(v) > 1))
    return report


def validate_assignment_coverage(assignment: list[int], n_nodes: int,
                                 n_workloads: int) -> ActionReport:
    """Every node assigned exactly once; every index a known workload."""
    report = ActionReport()
    if len(assignment) != n_nodes:
        report.add("assignment", "length-mismatch",
                   n_got=len(assignment), n_nodes=n_nodes)
        return report
    for node, workload in enumerate(assignment):
        if isinstance(workload, bool) or not isinstance(workload, numbers.Integral):
            report.add("assignment", "non-integer-entry", node=node, value=workload)
        elif not 0 <= int(workload) < n_workloads:
            report.add("assignment", "unknown-workload", node=node, value=workload)
    return report


def validate_finite_vector(values: list[float], name: str) -> ActionReport:
    """Reject NaN / ±inf / non-numeric entries (temperatures, powers, slopes)."""
    report = ActionReport()
    for i, value in enumerate(values):
        if not _finite(value):
            report.add(name, "non-finite-value", index=i, value=value)
    return report
