# REVIVAL_DECISIONS.md — Phase 0 Decisions Required Before Implementation

> Source revision `a8aec0c`. Each decision states options, audit recommendation,
> and what blocks Phase 1 if undecided. Nothing here modifies existing code.

## D-01 Scope: research framework, engineering workbench, or both?
- Options: (a) research-first (claims + stats rigor); (b) workbench-first (modular tool);
  (c) both, phased (recommended).
- Recommendation: (c) — P1–P2 rebuild the harness and metrics (serves both), P3–P4 re-prove
  claims, P5 builds the workbench UI/API on the proven core.
- Blocking: yes — determines acceptance criteria for every milestone.

## D-02 Legacy baseline: freeze or fix?
- Options: (a) byte-freeze `Scripts/` as `legacy/` reference (recommended);
  (b) fix in place.
- Recommendation: (a). The audit found guard/fallback asymmetries (C-01/C-02) that make
  in-place fixes claim-shifting. Preserve `a8aec0c` output as the comparator; build v2 beside it.
- Blocking: yes — sets repo layout for all of Phase 1.

## D-03 SLO definition (Gradient in or out? one definition everywhere?)
- Options: (a) Gradient is batch (AXION semantics, exempt); (b) Gradient is SLO-bound
  (TATS semantics, `inf`+guard); (c) per-workload SLO table with classes (recommended).
- Recommendation: (c) — `SLO = {class: L_MAX | None}`; Gradient defaults to batch;
  every metric labels which definition it used. Restate H-03/H-07 under the unified table.
- Blocking: yes — fairness harness (E-03) cannot be built without it.

## D-04 Work conservation as hard invariant?
- Options: (a) hard invariant — schedulers may permute and cap, never substitute
  (recommended); (b) substitution allowed but metered as work-loss.
- Recommendation: (a) for all thermal/SLO claims; (b) only inside explicitly labelled
  load-shedding experiments with work-loss endpoints. TATS fallback + ECM scheduler must
  be rewritten accordingly.
- Blocking: yes — determines optimizer action spaces.

## D-05 Physics fidelity target: toy demonstrator or calibrated model?
- Options: (a) labelled toy (document all constants as tuning assumptions);
  (b) calibrated (fit to metered facility/lab data); (c) toy now + calibration interface later (recommended).
- Recommendation: (c) — E-05 battery first; add a `FacilityParams` loader so future
  calibration doesn't re-architect. Sub-ambient HVAC and net-negative cooling power must
  be fixed regardless (floor asserts or chiller model).
- Blocking: partially — E-05 proceeds under (a); hardware claims need (b).

## D-06 PBD: controller, monitor, or removed?
- Options: (a) keep dual-gate as controller; (b) monitor-only with logged triggers;
  (c) recalibrate via E-06 then decide (recommended).
- Recommendation: (c) with prior toward (b) — current floor (3.70 °C/s) exceeds the
  canonical burst slope (3.33 °C/s), so (a) is currently unjustified.
- Blocking: yes for any burst-safety headline.

## D-07 Tucker in the decision path: keep, ablate, or demote to analysis?
- Options: (a) keep with current ranks; (b) E-07 ablation then decide (recommended);
  (c) demote to offline analysis immediately.
- Recommendation: (b) — the tensor (184k floats) is small enough that Tucker must prove
  marginal value over physics+Welford. Sensor-rank 4 and workload-rank 6 (no compression)
  are unjustified until E-07 says otherwise.
- Blocking: yes for the "tensor scheduling" identity claim.

## D-08 Statistics standard: trial-level paired tests with pre-registered endpoints?
- Options: (a) keep per-step tests; (b) trial-level (≥10 seeds) paired tests + CIs +
  pre-registered primary endpoints (recommended).
- Recommendation: (b); per-step series become diagnostics, never inference inputs.
- Blocking: yes — no claim is re-issued under (a).

## D-09 ECM scope: transfer-learning framework or 5-parameter pre-fit?
- Options: (a) keep full narrative (SVD fingerprint + deployment domains);
  (b) rescoped pre-fit baseline evaluated in the real simulator (recommended pending E-09);
  (c) retire.
- Recommendation: (b) — the SVD is currently unused by `fit()` and the evaluation physics
  differs from the main simulator; the deployment-domain list (10 industries) is unsupported.
- Blocking: yes for any transfer headline.

## D-10 Throughput definition: power proxy or work metric?
- Options: (a) keep `Σcap·P/ΣP` and mean-power; (b) work-based (jobs/FLOPs completed,
  cap-compensated latency) (recommended).
- Recommendation: (b) — power-proportional throughput plus heat-rewarding ECM metric
  (C-04) cannot survive contact with real scheduling.
- Blocking: yes for throughput/SLO joint claims.

## Decision log (to fill in review)
| ID | Decision | Owner | Date | Outcome |
|---|---|---|---|---|
| D-01 … D-10 | | | | |
