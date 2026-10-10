# METRICS_SPECIFICATION.md — P2.5 Canonical Metrics (units, denominators, missing values)

> Module: `src/axion/metrics/canonical.py` (controller-agnostic, trajectory-only;
> never alters state). Legacy `Metrics` classes retained untouched for reproduction.
> Tests: `tests/test_canonical_metrics.py` (9/9 PASS, synthetic ground truths).
> Machine units table: `canonical.UNITS`.

## A. Useful work (`WorkSummary`)

Offered/completed/rejected/dropped/failed/pending/substituted counts with
`retention = completed/offered` (**`None` on zero offered** — no fake 100%).
Substitution is recorded, never completion. Aggregate-only simulators report
multiset-level substitution counts with the job-level limitation documented.

## B. SLO (`SLOResult`, builds on Phase 1 tri-state validator)

Fields: `scope` (e.g. `inference:L_MAX=19.5ms`, `legacy-tats:all-workloads`),
`evaluated/satisfied/violated/unresolved`, plus `removed_before_evaluation`
(work dropped/substituted away — a 100% compliance with nonzero removal is
reported with the removal, never as pure success).
`compliance = satisfied/(satisfied+violated)` over decidable units; **`None`
when nothing is decidable**. Gradient stays unresolved until a service contract
exists (D-03) — unresolved is not a pass.

## C. Thermal risk (`thermal_risk`)

Peak, time-weighted mean; with threshold: time-above (s), max exceedance (°C),
integrated dose `Σmax(0,T−θ)·dt` (°C·s), up-crossing count under the documented
rule (`T[t−1] ≤ θ < T[t]` on the node-max series; trajectories starting hot count
the open event), per-event durations. Peak change and dose change reported
separately — a lower peak with equal dose is not a exposure reduction. Thresholds
are experimental criteria (65/60 °C legacy values labeled as such, not as
hardware safety limits).

## D. Cooling/resources (`CoolingSummary`, `percent_change`)

Device + auxiliary joules separately; water in litres with `water_is_proxy=True`
and baseline-anchored `water_reduction_pct` (**`None` on zero/unknown baseline** —
the "100% reduction from 0" artifact is unrepresentable). `percent_change`
returns `None` on zero baseline. Heat-removed is exposed ONLY when a COP-backed
model exists (none today — field absent by design, not zero).

## E. Fairness/reporting rules

Consistent windows/denominators/initial conditions per comparison (Phase 3 harness
duty); explicit units; documented aggregation; missing → `None`; non-finite
trajectories rejected loudly (`ValueError`), never scrubbed.

## Historical → canonical mapping

| Historical headline metric | Canonical replacement | Status |
|---|---|---|
| TATS/AXION mean-peak ΔT | `thermal.peak_mean` + `thermal.dose` (needs trajectories) | redefined (values reproduced; dose NOT TESTABLE from stdout) |
| Cooling-event counts | `thermal.crossing_count` + durations under stated rule | redefined (edge-rule counts reproduced; durations NOT TESTABLE) |
| SLO % (both scopes) | `slo.compliance` + scope + denominator + removal count | redefined (TATS 100% = guard scope; baseline 0.0% = bound-all scope) |
| Throughput retention % | `work.retention` (offered denominator) | redefined (power-proxy values reproduced; work-based values NOT TESTABLE) |
| Water/energy −98.8%/−100% | `cooling` proxy fields, baseline-anchored | redefined as proxies (physical-savings reading unsupported) |
| ECM RMSE (fit) | `fit.rmse` (fit quality, not thermal outcome) | redefined |
| ECM cooling/throughput (static) | — | **non-comparable** (static lookups can't feed trajectory metrics) |
| Paper §4.2 "97.5%, −5.9%" | — | **non-comparable** (no provenance to any recorded observable) |
| "Over 10 °C" (Explanation) | — | **contradicted** (no artifact; max executed Δ ≈ 8.06) |
