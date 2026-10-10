"""Legacy compatibility adapters: bind validators to actual legacy definitions.

All values (workload names/latencies, SLO scope, allowed caps, HVAC levels,
rack counts) are read from ``Scripts/core.py`` at call time — never
duplicated as constants here. Importing ``core.py`` is side-effect free
(constants + class definitions only).

Hard rule: this module must never import the legacy *simulation* modules
(``tats_simulation``, ``axion``, ``ecm_simulation``) in-process. Those modules
reseed the global ``random`` / ``np.random`` state at import time and execute
solver code with import-time globals; they run only as isolated subprocesses
via :mod:`axion.experiments.runner`. :func:`forbid_simulation_import` exists so
tests can pin that rule.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

from axion.config.legacy_config import load_core
from axion.constraints import slo as slo_mod
from axion.constraints import workload_accounting as wa
from axion.constraints import actions as acts

FORBIDDEN_LEGACY_MODULES = ("tats_simulation", "axion", "ecm_simulation")


def forbid_simulation_import(name: str) -> None:
    """Raise if ``name`` is a legacy simulation module (in-process import ban)."""
    if name in FORBIDDEN_LEGACY_MODULES:
        raise ImportError(
            f"in-process import of legacy simulation module {name!r} is forbidden: "
            "it reseeds global RNG state. Use axion.experiments.runner (subprocess).")


def default_scripts_dir(repo_root: str | Path) -> Path:
    return Path(repo_root) / "Scripts"


def load_legacy(scripts_dir: str | Path) -> ModuleType:
    """Load ``Scripts/core.py`` (safe) — simulation modules stay out of process."""
    return load_core(scripts_dir)


def workload_names(core: ModuleType) -> list[str]:
    return [str(n) for n in core.CFG["WORKLOAD_NAMES"]]


def build_legacy_slo_table(core: ModuleType) -> list[slo_mod.WorkloadSLO]:
    """SLO table from legacy truth, with the Gradient conflict marked UNRESOLVED.

    Legacy facts (executed check in Phase 0/1): ``W_LAT[5] = 24 ms``,
    ``L_MAX = 19.5 ms``, ``SLO_SENSITIVE = [0..4]`` (Gradient exempt), hence
    ``ALLOWED_CAPS[5]`` is the full cap list while the inference SLO would
    allow none. The adapter marks index 5 unresolved instead of choosing a
    semantics: see D-03 (deferred to Phase 2).
    """
    names = workload_names(core)
    lats = [float(v) for v in core.W_LAT]
    lmax = float(core.CFG["L_MAX"])
    bound = set(int(w) for w in core.CFG["SLO_SENSITIVE"])
    table = slo_mod.build_table(names, lats, lmax, slo_bound=bound, unresolved={5})
    table[5] = slo_mod.WorkloadSLO(
        5, names[5], lats[5], None, None,
        reason=("legacy conflict: W_LAT=24ms > L_MAX=19.5ms would allow no caps, "
                "but legacy exempts Gradient from SLO_SENSITIVE (batch-job claim, "
                "axion.py:68-72). Unresolved pending D-03."))
    return table


def allowed_caps(core: ModuleType) -> list[list[float]]:
    """Allowed-cap sets straight from legacy ``ALLOWED_CAPS`` (source of truth)."""
    return [[float(c) for c in caps] for caps in core.ALLOWED_CAPS]


def check_step_conservation(offered: list[int], assigned: list[int]) -> wa.ConservationReport:
    """Aggregate conservation check for one observed step."""
    return wa.check_conservation([int(w) for w in offered], [int(w) for w in assigned])


def check_step_slo(core: ModuleType, assignment: list[int],
                   caps: list[float]) -> slo_mod.SLOReport:
    """Score one observed step under the legacy-derived SLO table."""
    return slo_mod.check_step([int(w) for w in assignment],
                              [float(c) for c in caps],
                              build_legacy_slo_table(core))


def check_step_actions(core: ModuleType, *, caps: list[float] | None = None,
                       job_types: list[int] | None = None,
                       hvac: list[int] | None = None,
                       assignment: list[int] | None = None) -> acts.ActionReport:
    """Validate whichever action components are provided; combine violations."""
    combined = acts.ActionReport()
    n_nodes = int(core.CFG["N_NODES"])
    n_workloads = int(core.CFG["N_WORKLOADS"])
    if caps is not None and job_types is not None:
        sub = acts.validate_caps([float(c) for c in caps],
                                 [int(w) for w in job_types],
                                 allowed_caps(core))
        combined.violations.extend(sub.violations)
    if hvac is not None:
        sub = acts.validate_hvac([int(v) for v in hvac],
                                 int(core.CFG["N_RACKS"]),
                                 [int(v) for v in core.CFG["HVAC_LEVELS"]])
        combined.violations.extend(sub.violations)
    if assignment is not None:
        sub = acts.validate_assignment_coverage([int(w) for w in assignment],
                                                n_nodes, n_workloads)
        combined.violations.extend(sub.violations)
    return combined


def legacy_config_summary(core: ModuleType) -> dict[str, Any]:
    """Small JSON-able summary of legacy config for manifests and docs."""
    return {
        "N_NODES": int(core.CFG["N_NODES"]),
        "N_RACKS": int(core.CFG["N_RACKS"]),
        "SIM_STEPS": int(core.CFG["SIM_STEPS"]),
        "SCHED_PERIOD": int(core.CFG["SCHED_PERIOD"]),
        "L_MAX": float(core.CFG["L_MAX"]),
        "WORKLOAD_NAMES": workload_names(core),
        "WORKLOAD_POWER": [float(v) for v in core.W_POW],
        "WORKLOAD_LAT": [float(v) for v in core.W_LAT],
        "ALLOWED_CAPS": allowed_caps(core),
        "POWER_CAP_LEVELS": [float(v) for v in core.CFG["POWER_CAP_LEVELS"]],
        "HVAC_LEVELS": [int(v) for v in core.CFG["HVAC_LEVELS"]],
    }
