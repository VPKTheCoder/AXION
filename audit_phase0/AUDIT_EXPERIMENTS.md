# AUDIT_EXPERIMENTS.md — Phase 0 Reproducibility, Statistics & Required Experiments

> Source revision `a8aec0c`. Read-only; no experiment was executed in this audit.
> For every headline result below: exact script + inputs + baseline + metric + stats
> are identified, and the missing evidence for independent reproduction is listed.

## 1. Reproducibility inspection (observed facts)

| Item | TATS (`tats_simulation.py`) | AXION (`axion.py`) | ECM (`ecm_simulation.py`) |
|---|---|---|---|
| Seeds | `random 42 / np 42`; physics `seed=0` ×2 | `random 123 / np 123`; physics `seed=0` ×3 | `random 0 / np 0`; obs sampling via global `np.random` |
| Trials | **1** (600-step single run) | **1** (600-step single run) | 20 draws/K in `run()`, 50 in `stat_test`, 25 in `rmse_curves` |
| Scenario | `demand()` fixed bursts 150–259 / 350–449 | Same `demand()` | Different bursts 60–99 / 140–179 + static profiles |
| Raw data saved | None | None | None |
| Stats | Welch `ttest_ind(equal_var=False)` on steps; Cohen d pooled; Welch CI (`tats:396-406,515-525`) | Paired `ttest_rel` on steps; paired d; paired CI (`axion:496-505`) | One-sample t of RMSE vs 0.5 °C (`ecm:232`); reliability % |
| Plots | 8-panel PNG to `Assets/` | 8-panel PNG (+summary text) to `Assets/` | 8-panel PNG to `Assets/` (+ optional artifact dir) |

Cross-cutting gaps: unpinned deps (`requirements.txt`); no run manifest (code version,
seed, hostname, wall time beyond printed strings); committed PNGs are outputs masquerading
as inputs; no saved RNG state; no data dictionary for any metric.

## 2. Statistical critique (reasoned hypotheses, not executed tests)

1. **Independence violated (TATS + AXION).** Per-step `T_peak` with `τ≈3 s` and
   `SCHED_PERIOD=30 s` is strongly autocorrelated; treating 600 steps as 600 independent
   samples understates SE and inflates t/d. The "p≈0, d=2.82" style headlines are
   uninterpretable until recomputed at *trial level* (≥10 seeds) or with block-bootstrap / HAC SEs.
2. **Paired vs Welch inconsistency.** TATS uses independent-samples Welch; AXION uses paired —
   on the same kind of paired-by-step design with identical initial conditions. At most one
   choice is principled; neither handles autocorrelation. Standardize on trial-level paired tests.
3. **Count data without uncertainty.** Cooling events (465→0, 328→4, 300→0) are reported as
   point counts from a single run with no CI, no rate model, and (TATS/AXION vs ECM) different
   counting rules. Treat as Poisson/negative-binomial rates over seeds.
4. **ECM tests the wrong stochastic object (correctly) but overclaims the deterministic one.**
   `stat_test` properly targets RMSE (the stochastic quantity) — good — but the adjacent
   "throughput gain +38 %" is deterministic given a fitted profile and gets no uncertainty
   at all. Both need seed-swept CIs.
5. **No multiplicity control.** Dozens of panel comparisons (racks, K values, facilities)
   with per-comparison α=0.05 and no correction. Future reporting should pre-register primary
   endpoints (ΔT_peak-mean, cooling rate, SLO rate, retention) and correct the rest.

## 3. Experiments needed to validate or refute the claims

> Each experiment lists: question, protocol, arms, primary endpoints, acceptance sketch.
> All are **proposed** (none executed here). Estimated scale assumes the current 600-step,
> 32-node simulator (≈ seconds per run on the reference laptop class).

### E-01 Reproduction harness + run manifests (enables everything else)
Rebuild a clean runner that logs `{code_rev, CFG JSON, seeds, demand trace, per-step
T/P/cap/perm/cooling CSV, summary JSON}` to untracked `results/<ts>/`. Reproduce H-01–H-10
point estimates within tolerance before any redesign. *Accept:* rerun reproduces committed
direction of effect; manifest schema frozen as v2 contract.

### E-02 Stochastic variance (seeds × SA draws)
Fixed scenario, physics seeds 0–9 × SA seeds 0–9 (≥10 trials/arm) for TATS and AXION.
Report trial-level mean ΔT_peak with 95 % CI, cooling-rate CI, SLO-rate CI, retention CI.
*Accept:* effect persists with CI excluding 0; SA variance component quantified.

### E-03 Fair-harness reruns (conservation + unified SLO + identical observations)
(a) Instrument substitution rate (fraction of node-steps where assignment ≠ permutation of
demand or guard/fallback fires). (b) Rerun all arms under one SLO definition (state whether
Gradient is in-scope) and one observation model (both see noisy sensors or both see truth).
(c) Add conserving-only TATS variant (swap-only fallback). *Accept:* thermal benefit
decomposed into routing vs work-reduction vs guard components; headline SLO numbers restated.

### E-04 Demand generalization (held-out bursts)
Randomize burst position/type/intensity; add Poisson-arrival and diurnal scenarios; hold out
≥3 traces never used during tuning. *Accept:* ΔT_peak and cooling-rate CIs reported per
trace; no claim survives on the tuning trace alone.

### E-05 Physics battery (equilibrium / energy / coupling / DT-convergence / thresholds)
Closed-form and ledger tests from AUDIT_SCIENCE §4 (E-05a–e). *Accept:* criteria in that
table; failures gate any physics-dependent claim.

### E-06 PBD calibration (precision/recall + ablation)
Injected bursts with known onsets; sweep floor × adaptive on/off; report latency-to-detect,
false-positive rate per 1000 quiescent steps, and downstream ΔT_peak vs no-PBD control.
*Accept:* operating point with recall ≥ 0.9 at ≤ 1 FP/1000 steps, or PBD retired to monitor-only.

### E-07 Predictor fidelity + Tucker ablation
Log `T_pred − T_sim` per decision; compare SA with Tucker trust {0, ramp, 1} and ranks
{(16,4,48,6), (4,2,8,3), none}; report filled-only RMSE + downstream endpoints.
*Accept:* Tucker arm beats physics-only by a pre-registered margin or is removed from the
decision path (kept as analysis tool only).

### E-08 Optimizer isolation (greedy vs SA vs random)
Same-state comparisons; multi-seed SA variance; wall-time budget parity (e.g. equal ms).
*Accept:* SA's marginal ΔT_peak over greedy quantified; keep/replace decision data-driven.

### E-09 ECM in the real simulator (transfer honesty)
Plug ECM-fitted profiles into the RK4 loop (not static lookup); compare static-lookup vs
dynamic scores; ablate SVD fingerprint vs pure 5-parameter least squares; log design-matrix
condition numbers vs K. *Accept:* RMSE < 0.5 °C *and* dynamic cooling/throughput benefit
replicate, or ECM rescoped to "linear pre-fit baseline."

### E-10 Metric repair (dose + absolute water + work-based throughput)
Recompute all runs with exceedance-dose `Σmax(0,T−T_SAFE)·dt`, absolute litres, per-step WUE
distributions, and work-completing throughput (jobs×FLOPs or cap-compensated). *Accept:*
no headline survives solely via denominator effects (C-04).

## 4. Plot-generation audit
All figures are matplotlib `Agg` scripts with bespoke dark-theme code (~100 lines each),
no data export, no plot-vs-CSV consistency check, and (ECM) an environment-variable-gated
second save path. Propose: one tested `viz` module reading run-manifest CSVs; figures
regenerate deterministically from manifests; PNGs never committed (roadmap P1/P4).
