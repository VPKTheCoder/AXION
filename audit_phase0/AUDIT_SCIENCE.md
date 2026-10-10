# AUDIT_SCIENCE.md — Phase 0 Physics, Numerics & Algorithm Audit (AXION)

> Source revision `a8aec0c`, branch `main`. Read-only; no simulation was executed
> except two stdlib arithmetic checks noted below. Every "test" in §4–§5 is a
> *designed, not executed* verification protocol — do not read any of them as passed.

## 1. Governing equations as documented vs as implemented

Documented (`README.md:31-35`, paper §2.1):

```text
C_i dT_i/dt = P_i - (T_i - T_in)/R_amb - Σ_j (T_i - T_j)/R_ij
```

Implemented (`core.py:118-121`):

```python
Q_amb   = (T - T_in)/CFG["R_AMB"]            # shape (N,)
Q_inter = np.sum((T[:,None]-T[None,:])/self.R_mat, axis=1)
return (P_eff - Q_amb - Q_inter)/CFG["C_THERMAL"]
```

with `T_in` from `rack_inlet()` (`core.py:108-116`):

```python
T_in[rack] = T_AMBIENT + K_BYPASS * Σ P_eff[rack] - HVAC_DEGREE_PER_LEVEL * hvac[rack]
```

Match: the ODE kernel faithfully implements the documented equation, including the
off-diagonal coupling sum (diagonal excluded via `R=inf`, `core.py:77,81`).

## 2. Physics audit

### P-01 [Potential issue requiring a test — High] Parameter provenance is absent; the operating point looks tuned, not measured
Evidence: `core.py:17-22` — `C_THERMAL=90.0 J/K`, `R_AMB=0.145 K/W`,
`R_INTRA_RACK=0.40`, `R_INTER_RACK=4.00`, `K_BYPASS=5e-5 K/W`, `P_COOLING=280 W`,
`T_INIT_MU=44 ± 4 °C`, rack gradient `+3 °C/rack` (`core.py:100`), clip `60 °C` (`core.py:101`).
No citation, datasheet, or calibration note anywhere in the repo.
Executed stdlib check: `τ_iso = C·R_amb = 13.05 s`; with coupling,
`R_eff ≈ 0.035 K/W → τ_eff ≈ 3.2 s` (consistent with the `τ_eff≈2.6–3.2 s` strings
in `tats:424`, `axion:106-108`). Burst `ΔP=300 W → dT/dt ≈ 3.3 °C/s`; steady-state
`ΔT = 300 × 0.035 ≈ 10.5 °C` per hot job — i.e. the chosen constants place bursts
exactly in the regime where a 30 s scheduler fails and a fast path looks necessary.
This internal consistency is *not* validation: it shows the model can produce the
narrative, not that it represents any real rack.
Verification: E-05 (equilibrium/energy-balance/step-convergence battery) + a parameter
provenance table mapping each constant to a source or a "tuning assumption" label.

### P-02 [Confirmed issue — Medium] HVAC term can drive inlet below ambient with only a token fan cost
Evidence: `core.py:114-115`; executed check: max bypass `K_BYPASS·ΣP = 5e-5·2960 ≈ 0.148 °C`
vs HVAC authority `0.5 °C/level × 3 = 1.5 °C`. At full HVAC, `T_in ≈ 24 + 0.15 − 1.5 ≈ 22.65 °C`.
Fan energy is `15·Σhvac² W` (`axion.py:366`) — at most 540 W/rack vs IT power ~1–3 kW/rack.
Reasoning: sub-ambient inlet from a fan-only proxy is unphysical (fans move air; they do
not refrigerate it below ambient without a chiller model), and the optimizer is free to
exploit it because the objective charges only `OBJ_ETA=0.10` per HVAC level (`core.py:43`).
Uncertainty: medium — whether SA actually exploits this needs a run with HVAC-level logging.
Verification: E-05c (inlet-floor test: assert `T_in ≥ T_AMBIENT` unless a chiller model is added)
plus ablation with HVAC disabled.

### P-03 [Potential issue requiring a test — Medium] Cooling-event logic conflates detection, power subtraction, and energy ledger
Evidence: `core.py:123-139` — `cooling_on = T > T_SAFE` evaluated *before* the RK4 step;
events counted on rising edge (`cooling_on & ~prev`, `core.py:127`); `P_actual = P_eff − 280 W`
on hot nodes (`core.py:131`); energy accumulated as `280·n_hot·dt` (`core.py:128`);
temperature clipped to `[T_AMBIENT, 110]` (`core.py:138`).
Reasoning: edge-triggered counting understates sustained excursions (a node hot for 50
consecutive steps counts 1 event); the 280 W subtraction can exceed the node's own power
(40 W Embed → net −240 W, i.e. active refrigeration); the 110 °C clip silently absorbs
runaway trajectories that should fail loudly.
Verification: E-05b (sustained-excursion counting variants), E-05a (energy ledger:
`ΣC·ΔT` vs `Σ(P − Q)` closure), and a no-clip instability probe.

### P-04 [Design limitation — Medium] Initialization + sensor model are inconsistent across headline comparisons
Evidence: init `N(44 + 3·rack, 4)` clipped to `[25, 60]` (`core.py:96-101`) — rack 3 starts
≈53 °C, already near `T_WARN=60`; `read_sensors()` adds fixed offsets (`−4, −2 °C`,
`core.py:154-155`) and global-RNG noise (`core.py:153-156`), and recomputes `T_in` from the
*un-capped* workload power (`core.py:151`); AXION bypasses sensors entirely (`axion.py:411` reads `phys.T`).
Reasoning: TATS sees noisy, biased sensors; AXION sees ground truth. The comparison is
not sensor-equivalent, and the hot-start initialization pre-loads cooling events into both arms.
Verification: E-03 (identical-initial-condition + identical-observation fair-harness reruns).

### P-05 [Potential issue requiring a test — Low] RK4 is correctly coded but its accuracy at DT=1 s is unevidenced
Evidence: standard RK4 tableau (`core.py:134-137`) with *frozen* `P_actual, T_in` across
sub-stages — a documented simplification (power held constant over 1 s, reasonable).
`h/τ ≈ 1/3.2 ≈ 0.3`, comfortably inside RK4's stability region, so blow-up is unlikely;
but no convergence test (DT halving) exists, and the `[T_AMBIENT, 110]` clip would mask
an unstable scheme anyway.
Verification: E-05d (DT ∈ {1.0, 0.5, 0.25, 0.125} trajectory convergence + clip-hit counter).

## 3. Algorithmic correctness

### A-01 [Confirmed issue — High] TATS's "work-conserving" claim is contradicted by its own fallback and guard
Evidence: `tats:296-300` — on SA rejection, the hottest 25 % of nodes are *overwritten*
with `argmin(W_POW)` (Embed): `self.asgn[hot] = int(np.argmin(W_POW))`. `tats:316-322` —
any Gradient assignment is overwritten with the lowest-power SLO-feasible workload.
Both are substitutions (work destroyed/redefined), not permutations (work moved).
The between-step safety path (`tats:306-314`) *does* swap (conserving) — so the file
contains both semantics side by side.
Reasoning: any cooling/SLO benefit measured on steps where the fallback or guard fires
is partly a work-reduction benefit, and the baseline (which always runs `demand()`
verbatim, `tats:437`, including Gradient) pays full power on those same steps.
Verification: E-03 (instrument fraction of steps/nodes where fallback/guard fires; rerun
with a conserving-only variant).

### A-02 [Potential issue requiring a test — High] PBD threshold + adaptive gate may rarely fire — the "burst safety" story is unevidenced
Evidence: `core.py:40` — `PBD_THRESH = 0.90·370/90 = 3.70 °C/s`. Executed check: a 300 W
burst gives `ΔP/C ≈ 3.33 °C/s < 3.70`. Docstrings disagree: `axion.py:46-49` says
"≈3.3 °C/s … 5 s costs ~16 °C" while `Notes/Project_AXION_Explanation.md:40-41` claims
a "hard floor (e.g. 3.0 °C/s)". The runtime gate requires *both* `slope > 3.70` *and*
`slope > rolling-mean + 2σ` (`axion.py:259-263`), where the rolling buffer includes the
current slope and the warmup default `adaptive=1e9` (`axion.py:262`) suppresses all firing
for the first 6 steps.
Reasoning: the physical floor alone excludes the canonical burst the narrative describes;
the adaptive term further suppresses firing during sustained hot regimes (mean adapts upward).
PBD trigger counts are reported (`axion:493-494`) but no precision/recall analysis exists.
Verification: E-06 (PBD firing-rate / precision-recall sweep over injected bursts; threshold ablation).

### A-03 [Potential issue requiring a test — High] SA predictor vs simulator mismatch (TATS three-source blend; AXION one-step linear model)
Evidence: TATS `_predict` (`tats:171-195`): `T_phys = T_now + ΔP·R_eff` (steady-state-gain,
single-step, no coupling dynamics, no inlet feedback, no cooling subtraction) blended with
Welford means and a Tucker table whose trust ramps over 5 refits (`tats:191`). AXION
`predict` (`axion:120-130`): same linear form plus `ΔT_in`, optional Tucker hook
(`tucker_table=None` in practice — never wired in `run()`).
Reasoning: the optimizer minimizes the *predictor's* objective while scoring uses the
*simulator's* RK4 + coupling + inlet + cooling dynamics. The paper's "Tucker-projected
placement" narrative overstates the mechanism: Tucker refits are fitted (`tats:283-290`)
and their RMSE is reported, but the decision-path weight starts at 0 and only reaches 1.0
after 5 refits (~step 150+ at SCHED_PERIOD=30/refit cadence 60 — i.e. mid-run).
Verification: E-07 (predictor-vs-simulator residual analysis; Tucker-ablated SA comparison).

### A-04 [Design limitation — Medium] Tucker geometry: ranks exceed signal on two modes; compression claim overcounts
Evidence: tensor `(32, 4, 240, 6)`, ranks `[16, 4, 48, 6]` (`core.py:34,46-47`).
Executed check: full size 184,320 floats; core 18,432 + factors 12,084 = 30,516 (~6×,
not the ~10× implied by core-only accounting in `tats:422-423`). Sensor rank 4 = full
sensor dim (no compression, and two sensor channels are near-duplicates `T−4, T−2`);
workload rank 6 = full workload dim (no compression). Time rank 48 over a 240-slot
deterministic rotation is generous.
Reasoning: the "curse of dimensionality → Tucker" framing is overstated for a
184k-float tensor that fits in L2 cache; the reported RMSE (`rmse_all` vs `rmse_filled`,
`tats:82-84`) mixes unfilled ambient slots with real data.
Verification: E-07 (rank-ablation: (4,2,8,3) vs current; report filled-only RMSE + downstream ΔT_peak).

### A-05 [Confirmed issue — Medium] SA complexes differ across scripts with no convergence evidence
Evidence: TATS: 1200 iters, swap-prob 0.20, τ_init 15 → cool 0.995 (`core.py:35-38`,
`tats:222-244`); AXION full 1500 / PBD 300 iters, 75 % cap-moves (`core.py:36`,
`axion:223-248`). No seed-sweep, no restarts, no best-of-N, no optimality-gap logging;
`conv_iters` records only early-exit (`tats:244`, never triggers before 1200 at 0.995
cooling from 15 → 0.01 needs ~1468 steps, so "convergence at ~1033" comment in `tats:10`
is itself suspect).
Reasoning: SA is the decision engine for both headline results, yet its stochastic
variance is unmeasured (single seed each).
Verification: E-02 (multi-seed SA variance on fixed states) + E-08 (greedy-only and
random-search baselines to isolate SA's marginal contribution).

### A-06 [Confirmed issue — High] ECM evaluates transfer with a different physics model than TATS/AXION
Evidence: `ecm:89-94` — `T = T_amb + rack_offset + P·R_amb`: a *static linear map* with
5 unknowns, no coupling, no inlet recirculation, no RK4, no cooling dynamics.
`LightTATS.evaluate` (`ecm:162-176`) scores assignments by table lookup with
`cool += any(T > T_SAFE)` per step — a different (stricter) cooling definition than
the edge-triggered per-node count in `core.py:127`.
Reasoning: ECM's RMSE/cooling/throughput numbers live in a different universe from the
TATS/AXION numbers; "transfer the thermal fingerprint" means "fit 5 linear coefficients,"
and the `tucker2` SVD fingerprint (`ecm:100-107`) is computed but never used by `ECM.fit`.
Verification: E-09 (evaluate ECM-fitted profiles inside the real RK4 simulator; ablate SVD vs pure least-squares).

## 4. Numerical verification battery (designed, NOT executed in Phase 0)

| ID | Test | Method | Acceptance sketch |
|---|---|---|---|
| E-05a | Equilibrium | Fix uniform P, run to steady state; compare against analytic `T* = T_in + P·R_eff`-with-coupling solve | ‖T_sim − T*‖ < 0.5 °C |
| E-05b | Energy balance | Per-step ledger `ΣC·ΔT − Σ(P−Q)·dt`; report drift | Relative drift < 1 % over 600 steps |
| E-05c | Coupling / inlet / HVAC | Two-node analytic coupling; rack-Q sweep; HVAC-level sweep with floor assert | Matches closed form; `T_in ≥ T_AMBIENT` unless chiller modeled |
| E-05d | Timestep convergence | DT ∈ {1, 0.5, 0.25, 0.125}, same scenario | Max-ΔT_peak halves with DT (1st-order-or-better observed); clip-hit count reported |
| E-05e | Threshold crossings | Controlled ramp through T_WARN/T_SAFE | Event counts match step-function truth under stated counting rule |

## 5. Algorithmic verification battery (designed, NOT executed)

| ID | Test | Method |
|---|---|---|
| E-06 | PBD precision/recall | Inject scheduled bursts of known onset; sweep floor ∈ {1,2,3,3.7,5} °C/s × adaptive on/off |
| E-07 | Predictor fidelity + Tucker ablation | Log per-decision `T_pred − T_sim`; compare SA with trust ∈ {0, ramp, 1} and ranks ablated |
| E-08 | Optimizer isolation | Same state → greedy-only vs SA vs random search; multi-seed variance |
| E-09 | ECM in the real simulator | Plug ECM profiles into RK4 loop; compare vs static-lookup scores |

## 6. Subsystem retention recommendations (science layer)

| Subsystem | Recommendation | Rationale |
|---|---|---|
| RK4 thermal core | Retain and refactor | Equation is right; needs provenance, energy ledger, floor asserts, convergence proof |
| Inlet/HVAC/cooling sub-models | Replace after validation | Sub-ambient HVAC + edge-counted cooling + net-negative P_actual need redesign against metered-facility data or explicit toy-model labels |
| TATS three-source predictor | Replace after validation | Keep Welford profiler (retain); Tucker-decision-path must earn its place via E-07 ablation |
| AXION cap/HVAC SA | Retain and refactor | Conserving formulation is the right one; needs variance analysis + greedy baseline isolation |
| PBD | Replace after validation | Concept is sound; current dual-gate thresholds look miscalibrated (E-06 decides) |
| ECM least-squares transfer | Retain and refactor | 5-parameter fit is a legitimate baseline; retire the unused-SVD + deployment-domain narrative until E-09 passes |
