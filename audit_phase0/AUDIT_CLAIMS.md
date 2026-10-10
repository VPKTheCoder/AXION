# AUDIT_CLAIMS.md — Phase 0 Invariants, Baseline Fairness & Headline-Claim Verification

> Source revision `a8aec0c`. Read-only; no simulation was executed.
> Classification key: **Confirmed issue** / **Potential issue requiring a test** /
> **Design limitation** / **Missing evidence** / **Improvement opportunity**.
> Verification status key: **UNVERIFIED** (no run in this audit, no raw data in repo)
> / **CONTRADICTED BY CODE** / **MIXED**.

## 1. Invariants: does the implementation guarantee them independently?

### C-01 [Confirmed issue — High] Workload conservation is guaranteed only by AXION; TATS and ECM break it
- AXION: conserving by construction. `load_balance` (`axion.py:160-190`) permutes the
  same `job_types` multiset (`perm[n]=j` bijection; fallback reassigns cap, not identity).
  Throughput loss comes only from caps (`retention = Σcap·P/ΣP`, `axion.py:354-356`). **Holds.**
- TATS: **violated**. Fallback overwrites hottest 25 % with Embed (`tats_simulation.py:296-300`);
  SLO guard overwrites Gradient with lowest-power feasible workload (`tats:316-322`).
  The between-step swap path (`tats:306-314`) conserves, but the two substitution paths do not.
- ECM `LightTATS.schedule` (`ecm_simulation.py:152-160`): per-node `demand[n] → safe workload`
  substitution (picks max-power *safe* workload, else `argmin(W_POW)`). **Violates.**
- Implication: any TATS/ECM "cooling eliminated" reading conflates *moving* heat with
  *removing* work. Proposed verification E-03 instruments substitution rate per run.

### C-02 [Confirmed issue — High] SLO feasibility is enforced asymmetrically, flattering the candidate arms
- TATS candidate: hard `inf` rejection in SA (`tats:205-207`) + post-hoc guard (`tats:318-322`)
  ⇒ candidate can never violate. TATS baseline: raw `demand()` including Gradient
  (24 ms > 19.5 ms ⇒ violates whenever scheduled, `tats:437-438`, `tats:361`). The paper's
  "baseline dropped to 97.5 %, AXION held 100 %" (§4.2) is therefore partly a measurement of
  the guard, not of thermal intelligence.
- AXION candidate vs baseline is cleaner: both scored by the same `L_eff=L_rated/cap` rule
  (`axion.py:345-352`), and the baseline's reactive throttle (`cap 0.5/0.3`, `axion.py:318-320`)
  is *allowed* to violate (correctly — emergency throttling should be scored honestly).
  But Gradient's exemption (`SLO_SENSITIVE=[0..4]`, `core.py:28`) means AXION's "100 %" is
  over a narrower SLO definition than TATS's. The two "100 %" claims are not comparable.
- Verification: E-03 (score all arms under one SLO definition; report violation *rate by cause*).

### C-03 [Potential issue requiring a test — Medium] Power-cap legality, resource constraints, safe fallback
- Cap legality: AXION SA samples only from `ALLOWED_CAPS[w]` (`axion.py:228`) and repairs
  infeasible inits (`axion.py:213-217`) — good. TATS SA mutates assignments, not caps, and
  relies on the `inf` + guard pair — good but substitution-flavoured (C-01).
- Resource constraints: no capacity model exists (any workload runs on any node; no memory/
  occupancy limits). "Valid assignment" = "SLO-feasible workload index" — a thin invariant,
  independently checkable but unrealistic. **Design limitation.**
- Safe fallback: TATS fallback (substitution) is thermally safe but not work-safe; AXION
  has no explicit fallback if SA returns `inf` everywhere (cannot happen here since caps exist
  for all SLO-sensitive workloads *except* the exempted Gradient — brittle). Needs a tested
  conserving fallback (e.g. identity + cap=1.0) with an alert counter.

## 2. Baseline fairness matrix (observed facts)

| Dimension | TATS vs baseline (`tats_simulation.py:427-438`) | AXION vs baselines (`axion.py:396-426`) | ECM naive/oracle (`ecm:190-215`) |
|---|---|---|---|
| Workload multiset | **UNEQUAL when fallback/guard fires** (candidate substitutes; baseline never does) | Equal (all arms permute/substitute identically? AXION permutes, baseline identity — same multiset, different mapping: fair) | Equal multiset per evaluation, but scheduler substitutes in all arms |
| Initial conditions | Equal (`seed=0` both) | Equal (`seed=0` all three) | N/A (static profiles, no dynamics) |
| Action constraints | Candidate: SA + guard; baseline: none (runs hot AND violates SLO) | Candidate: caps+HVAC+LB; baseline: reactive throttle only; greedy: LB only — informative ablation, good | Naive: source profile; ECM: fitted; oracle: true profile |
| Information | Candidate sees sensors + history; baseline sees nothing (fair — that IS the intervention) but candidate also gets the guard | Candidate sees `T_now` exactly; baseline same observation, no optimizer (fair) | ECM sees K noisy samples; naive sees none (fair); oracle sees truth (upper bound, fair) |
| Scoring | Same `Metrics` instance type both arms (fair) but SLO definition punishes baseline by construction (C-02) | Same scorer (fair); retention metric `Σcap·P/ΣP` conflates cap-loss with throttle-loss — needs decomposition | Throughput = mean assigned power (higher=better) **rewards hotter schedules**; cooling counted as per-step `any()` — inconsistent with `core.py` edge counting |

### C-04 [Confirmed issue — Medium] Metrics can reward hidden work loss
- TATS `Metrics.slo_ok` is per-step boolean (`tats:361`); one Gradient anywhere fails the
  whole step — baseline fails many steps by construction while TATS's guard erases them.
- `total_water_L = dot(wue, e_it_kwh)` (`tats:382`, `axion:377`): WUE is computed from
  cooling power over IT energy (`tats:366-370`), so a candidate that *reduces IT power*
  (via substitution/capping) shrinks the denominator and can look water-efficient even if
  absolute cooling barely changes. Report absolute litres *and* per-step WUE distributions.
- ECM throughput (`ecm:176`, mean assigned power) is monotonically increasing in scheduled
  power — the opposite of a thermal penalty. A scheduler that always picks GEMM maximizes
  "throughput" while maximizing heat. Needs a capped-work or SLO-conditioned definition.

### C-05 [Design limitation — Medium] No temperature-unsafe-excursion penalty in headline metrics
Cooling *events* and *energy* are reported, but there is no metric for degrees × time above
`T_SAFE` (thermal dose), no worst-node trajectory, and no hardware-damage proxy. A controller
that rides `T_SAFE − ε` scores identically to one with 10 °C margin. Add exceedance-dose
(`Σmax(0, T−T_SAFE)·dt`) to the standard metric set (roadmap P1).

## 3. Headline-claim verification table

Status **UNVERIFIED** = no raw data in repo + no run performed in this audit.
"Script" = where the number would have to come from. "Missing evidence" = what blocks
independent reproduction.

| # | Headline claim (source) | Script / inputs / baseline / metric | Stat method | Status | Missing evidence |
|---|---|---|---|---|---|
| H-01 | TATS mean peak −8.06 °C (README:148, paper §4.1) | `tats:run`, demand `core:162-166`, reactive-identity baseline, mean(`T_peak`) | Welch t, Cohen's d pooled, Welch CI (`tats:514-525`) | **UNVERIFIED** | Raw `T_peak` series, seed sweep, DT-convergence, substitution-rate log |
| H-02 | TATS cooling 465 → 0, water → 0 (README:149-150, paper §4.1) | Same; edge-triggered per-node counts (`core:127`) | Counts, no CI | **UNVERIFIED + counting-rule caveat** (sustained episodes count once) | Event-definition doc, per-node trajectories, absolute litres |
| H-03 | TATS 100 % SLO (README:151) | Same; `slo_pct` (`tats:376`) | % steps | **MIXED — guard artifact (C-02)** | Violation-by-cause breakdown; conserving-only rerun |
| H-04 | Welch significant, large effect (README:152, paper d=2.82) | `ttest_ind(..., equal_var=False)` on 600 autocorrelated steps | p, d | **UNVERIFIED + method caveat** (independence violated) | Block-bootstrap / trial-level test over ≥10 seeds |
| H-05 | AXION 61.64 → 57.99 °C peak (README:160) | `axion:run`, same demand, reactive-throttle baseline | Paired t on steps (`axion:497-505`) | **UNVERIFIED** | Same as H-01 + HVAC ablation |
| H-06 | AXION cooling 328 → 4, −98.8 % water/energy (README:161-163) | Same | Counts, ledger (`core:128`) | **UNVERIFIED** | Same as H-02 |
| H-07 | AXION 100 % SLO, 96.4 % retention (README:164-165) | Same; `slo_pct`/`retention` (`axion:373-376`) | % | **UNVERIFIED (SLO scope narrower than TATS)** | Unified SLO definition; retention decomposed cap vs throttle |
| H-08 | ECM B RMSE 5.50 → 0.163 °C @K=20 (README:173) | `ecm:run/stat_test`, 20–50 draws, noise 0.3 | One-sample t vs 0.5 °C (`ecm:232`) | **UNVERIFIED (in static-model universe only)** | Condition-number log, RK4 transfer scores (E-09) |
| H-09 | ECM edge cooling 300 → 0 @K=20 (README:174) | Same; `any(T>T_SAFE)` per-step count | Means over 20 draws | **UNVERIFIED + definition differs from H-02/H-06** | Same-scorer comparison |
| H-10 | ECM hospital +38 % throughput; HPC near-oracle (README:175-176) | Same; mean-power "throughput" | Means | **UNVERIFIED + metric rewards heat (C-04)** | Work-based throughput definition |
| H-11 | Paper §4.2: baseline 97.5 % SLO, AXION 100 %, −5.9 % throughput | Paper narrative (matches AXION arm loosely) | Unstated | **UNVERIFIED, no provenance** | Which script/seed produced 97.5 % and 5.9 % (neither README number matches exactly) |
| H-12 | Explanation §Conclusion: "over 10 °C" reduction | `Notes/Project_AXION_Explanation.md:63` | Unstated | **CONTRADICTED BY CODE-adjacent numbers** (8.06 / 3.65 °C elsewhere; no 10 °C artifact) | Source run or correction |

## 4. Per-finding classifications (this document)

- C-01 work conservation: **Confirmed issue** (High). Verify E-03.
- C-02 asymmetric SLO: **Confirmed issue** (High). Verify E-03.
- C-03 fallback/capacity: **Potential issue** (Medium) + capacity **Design limitation**. Verify fallback fault-injection.
- C-04 metric perversity: **Confirmed issue** (Medium). Verify metric recomputation on logged trajectories.
- C-05 missing dose metric: **Design limitation** (Medium). Add in v2 metrics package.
- H-01–H-11: **Missing evidence** (all). H-12: **Confirmed issue** (doc contradiction).
