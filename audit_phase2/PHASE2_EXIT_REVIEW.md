# PHASE2_EXIT_REVIEW.md — Acceptance Verdicts (evidence-linked, failures visible)

## Model specification — SATISFIED

Actual equations/units documented (`THERMAL_MODEL_SPECIFICATION.md`,
`DIMENSIONAL_ANALYSIS.md`); equation↔code trace complete; assumptions classified
(specified/derived/assumption/unknown — zero calibrated parameters claimed);
replica fidelity pinned by executed test. ODE algebra dimensionally sound; three
implicit-unit coefficients flagged, not laundered.

## Numerical verification — SATISFIED

Analytical references executed (A–F all PASS): equilibrium 9.7e-13, RC response
2.3e-6, coupled solve 7.1e-14, 4th-order refinement (4.046/4.023/4.012) with DOP853
6e-11 agreement. Discontinuity behavior reported (finite, ledger-explicit), order
demands suspended there by design. No instability concealed; float32 rounding
characterized.

## Energy accounting — PARTIAL (valid partial, fully documented)

Ledger closes to quadrature theory (4.9e-4, 2nd-order) on supported quantities;
internal exchange verified zero; clips/cooling/water handled with explicit limits.
Incomplete as *physics* (no COP, no chiller, fan/water proxies unattributed) —
marked PARTIAL per the spec's own rule ("do not fabricate a workaround"), with the
missing quantities enumerated and the code refusing to equate device energy with
heat removed.

## HVAC and cooling — SATISFIED (as audit + guardrails; equations intentionally unchanged)

Bounds tested (10-case battery); inlet/ambient relations specified; sub-ambient
reachability proven exact (23.5 °C @ Q=0/hvac=1) and classified
`sub_ambient_unsupported` under the declared scope; emergency authority audited as
`abstract-control`. Unsupported mechanisms listed (5). No silent exploit path:
future controllers must consult `inlet_assessment`. No arbitrary penalties added.

## Metrics — SATISFIED

One canonical module with units/denominators/missing-value rules; 9/9 ground-truth
tests incl. zero-baseline, empty-denominator, unresolved-SLO, removal-reporting edge
cases. Substitution cannot count as completion; zero-baseline percents are
unrepresentable (`None`); proxies labeled. Historical→canonical mapping complete
(§E of METRICS_SPECIFICATION.md).

## Legacy reconciliation — SATISFIED

Three safe runs, figures untouched, canonical values computed only where observables
support them. Dispositions: 5 reproduced-as-records, 3 redefined, 2 non-comparable,
1 contradicted ("over 10 °C"), PBD not-testable with 0-trigger record. No
superiority judgment made (Phase 3).

## Regression and reporting — SATISFIED

59/59 Phase 1 tests still pass (one pre-existing invalid expectation — the
`ALLOWED_CAPS[5]` audit assumption — corrected and documented in Phase 1, not
weakened). 38 new tests pass (97 total, ×2 consecutive). All 10 required
deliverables exist (`audit_phase2/` 8 docs + this report + test report;
machine-readable JSON under `results/phase2/`). `Scripts/` + `Assets/` hashes
identical to Phase 1 records; `audit_phase0/` + `audit_phase1/` unchanged;
only tracked edit remains the Phase 1 `.gitignore` line.

## Unresolved / Phase 3 inputs

1. D-03 Gradient-SLO decision (blocks unified compliance restatement).
2. E-03 fair harness with trajectory capture (substitution rates, identical observations).
3. E-02 trial-level statistics; E-06 PBD rig; E-07 Tucker ablation; E-08 optimizer
   isolation; E-09 ECM dynamic scoring; chiller-model scope decision for sub-ambient use.
4. Physically validated ≠ established: every constant remains toy/heuristic — calibration
   against metered data is out of scope and unclaimed.

**Phase 2 is ready for review.** The foundation is trustworthy precisely where verified,
explicitly partial where the model cannot support more, and adversarial to its own
historical numbers wherever the evidence required it.
