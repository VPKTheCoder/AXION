"""Central metric definitions (name -> human-readable definition).

The runner attaches the relevant definitions to each manifest so that a
stored number is never separated from what it meant. Values are produced by
legacy scripts or future validators; this module defines *meaning*, not values.
"""

from __future__ import annotations

DEFINITIONS: dict[str, str] = {
    "mean_peak_temp_C": (
        "Mean over run steps of max node temperature (°C). "
        "Legacy TATS/AXION Metrics.T_peak."
    ),
    "worst_peak_temp_C": "Maximum over run steps of max node temperature (°C).",
    "cooling_events": (
        "Legacy edge-triggered count: increments once per node when cooling "
        "activates after being off (Scripts/core.py cooling_on & ~prev). "
        "Sustained hot episodes count once; differs from ECM's per-step any()."
    ),
    "cooling_energy_kJ": "Accumulated P_COOLING * n_hot * dt (Scripts/core.py ledger).",
    "total_water_L": "Sum over steps of WUE * E_IT (legacy derived quantity).",
    "slo_pct": (
        "Percent of steps scored SLO-compliant under the run's SLO scope. "
        "Scope MUST be recorded alongside (legacy TATS scope != AXION scope)."
    ),
    "throughput_retention_pct": (
        "AXION: 100 * sum(cap*P_job)/sum(P_job). TATS/ECM use different "
        "proxies; not comparable across experiments without scope notes."
    ),
    "rmse_C": "ECM profile RMSE vs true static profile (°C); static-model universe only.",
    "pbd_triggers": "AXION PBD mini-SA trigger count (dual-gate; see audit A-02).",
}

LEGACY_EXPERIMENT_METRICS: dict[str, tuple[str, ...]] = {
    "tats": ("mean_peak_temp_C", "worst_peak_temp_C", "cooling_events",
             "cooling_energy_kJ", "total_water_L", "slo_pct"),
    "axion": ("mean_peak_temp_C", "worst_peak_temp_C", "cooling_events",
              "cooling_energy_kJ", "total_water_L", "slo_pct",
              "throughput_retention_pct", "pbd_triggers"),
    "ecm": ("rmse_C", "cooling_events", "slo_pct", "throughput_retention_pct"),
}


def definitions_for(experiment: str) -> dict[str, str]:
    """Definition subset attached to a manifest for one experiment."""
    names = LEGACY_EXPERIMENT_METRICS.get(experiment, ())
    return {name: DEFINITIONS[name] for name in names}
