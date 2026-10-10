"""Work accounting: aggregate multiset checks plus an explicit job ledger.

Phase 0 finding C-01: TATS and ECM substitute workloads (hottest 25 % ->
Embed; Gradient -> lowest-power feasible; per-node demand -> safe workload)
while the narrative claims work conservation. A substitution must never be
recorded as though the original work was completed.

Two layers, matched to what the simulator can actually observe:

1. Aggregate layer (:func:`classify_step`, :func:`check_conservation`) works
   on legacy's representation — per-node workload indices with no job
   identities. It distinguishes a *permutation* (same multiset, rerouted —
   conserving) from a *substitution* (multiset changed — work redefined,
   explicitly recorded per node, never counted as completed).

2. Job layer (:class:`WorkLedger`) is the forward-looking ledger for
   implementations that carry job identities. Every offered job must end in
   exactly one terminal state; disappearance and duplication are errors.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ConservationReport:
    """Outcome of comparing offered vs assigned workload multisets."""

    kind: str  # "conserved-identity" | "conserved-permutation" | "substitution" | "truncated"
    conserved: bool
    substitutions: list[dict[str, int]] = field(default_factory=list)
    # each substitution: {"node": i, "offered": w, "assigned": w}


def classify_step(offered: list[int], assigned: list[int]) -> ConservationReport:
    """Classify one scheduling step from aggregate workload indices."""
    if len(offered) != len(assigned):
        return ConservationReport("truncated", False)
    subs = [{"node": i, "offered": int(o), "assigned": int(a)}
            for i, (o, a) in enumerate(zip(offered, assigned)) if int(o) != int(a)]
    if Counter(int(w) for w in offered) != Counter(int(w) for w in assigned):
        return ConservationReport("substitution", False, subs)
    if not subs:
        return ConservationReport("conserved-identity", True)
    return ConservationReport("conserved-permutation", True, subs)


def check_conservation(offered: list[int], assigned: list[int]) -> ConservationReport:
    """Alias with validator naming (see :func:`classify_step`)."""
    return classify_step(offered, assigned)


# ---------------------------------------------------------------------------
# Job-level ledger (for controllers that carry job identities)
# ---------------------------------------------------------------------------

TERMINAL = ("completed", "rejected", "dropped", "failed")


@dataclass
class OfferedJob:
    job_id: str
    workload: int


class LedgerError(ValueError):
    """Raised for duplication, disappearance, or illegal transitions."""


class WorkLedger:
    """Explicit ledger: offer -> assign -> terminal-state, no silent loss.

    A *substitution* (assigning a different workload than offered) is recorded
    via :meth:`substitute` and forces the terminal state to be one of
    rejected/dropped/failed — never ``completed``.
    """

    def __init__(self) -> None:
        self._offered: dict[str, int] = {}
        self._assigned: dict[str, int] = {}
        self._terminal: dict[str, str] = {}
        self._substituted: dict[str, int] = {}

    def offer(self, job: OfferedJob) -> None:
        if job.job_id in self._offered:
            raise LedgerError(f"duplicate offer of job {job.job_id!r}")
        self._offered[job.job_id] = int(job.workload)

    def assign(self, job_id: str, workload: int) -> None:
        if job_id not in self._offered:
            raise LedgerError(f"assign of unoffered job {job_id!r}")
        if job_id in self._terminal:
            raise LedgerError(f"assign of terminal job {job_id!r}")
        self._assigned[job_id] = int(workload)

    def substitute(self, job_id: str, new_workload: int) -> None:
        """Record that the offered workload was replaced, not completed."""
        if job_id not in self._offered:
            raise LedgerError(f"substitute of unoffered job {job_id!r}")
        self.assign(job_id, new_workload)
        self._substituted[job_id] = int(new_workload)

    def finish(self, job_id: str, state: str) -> None:
        if state not in TERMINAL:
            raise LedgerError(f"unknown terminal state {state!r}")
        if job_id not in self._offered:
            raise LedgerError(f"finish of unoffered job {job_id!r}")
        if job_id in self._substituted and state == "completed":
            raise LedgerError(
                f"substituted job {job_id!r} must never be recorded as completed")
        self._terminal[job_id] = state

    def audit(self) -> dict[str, object]:
        """Every offered job accounted for exactly once; gaps listed explicitly."""
        missing_terminal = sorted(j for j in self._offered if j not in self._terminal)
        unassigned = sorted(j for j in self._offered
                            if j not in self._assigned and j not in self._terminal)
        return {
            "n_offered": len(self._offered),
            "n_terminal": len(self._terminal),
            "n_substituted": len(self._substituted),
            "complete": not missing_terminal,
            "missing_terminal": missing_terminal,
            "finished_without_assignment": unassigned,
            "substituted": dict(self._substituted),
        }
