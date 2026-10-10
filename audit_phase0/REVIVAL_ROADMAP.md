# REVIVAL_ROADMAP.md — Phase 0 Proposed v2 Architecture & Phased Plan

> Source revision `a8aec0c`. Proposal only — no code was changed in this audit.
> Measurable acceptance criteria gate every phase. Legacy `Scripts/` stays frozen
> as the scientific baseline (D-02).

## 1. Engineering assessment (current state, observed)

Modularity: low — three forked scripts + one shared `core.py`; wildcard imports;
duplicate inlet/metric/plotting code. Configuration: single untyped global `CFG`,
no validation, no per-run overrides. Interfaces: none (no functions/classes exported
as a library; everything runs on import-time globals). Error handling: near-absent
(`lstsq` on possibly singular K=5 designs, SA `inf` handling ad hoc, clips mask
instability). Testing: zero. Logging: print statements only; no run manifests.
Dependencies: unpinned (`numpy scipy matplotlib tensorly`), no Python floor.
Local execution: `pip install -r requirements.txt` + `python Scripts/*.py`, which
overwrites tracked `Assets/*.png` by design.

## 2. Proposed v2 architecture (module responsibilities, independent by construction)

```text
axion_v2/
  physics/       RK4 thermal network + inlet/HVAC/cooling sub-models; energy ledger;
                 floor asserts (T_in ≥ T_amb unless chiller); DT-convergence tested (E-05)
  workloads/     Scenario library: deterministic demand traces, burst randomizer,
                 Poisson/diurnal arrivals; held-out set (E-04)
  sensors/       Observation models (truth / noisy-biased); per-instance RNG ownership
  predictors/    Welford profiler (retain); linear physics projector; Tucker manifold
                 (optional, E-07-gated); all expose predict(T_now, action) → T_pred + residuals
  controllers/   Greedy-LB (retain); cap/HVAC SA (retain+refactor, variance-tested);
                 PBD monitor (E-06-gated promotion to controller); conserving fallbacks only
  constraints/   SLO table (D-03), ALLOWED_CAPS validation (non-empty), assignment
                 validity, exceedance-dose accounting; hard-invariant checker (D-04)
  experiments/   Trial runner (seed grids), run-manifest writer (params+CSV+JSON),
                 fair-harness (identical init/obs/scorer, E-03), metric repair (E-10)
  viz/           Single tested plotting module regenerating figures from manifests; never commits outputs
legacy/          Byte-frozen copy of Scripts/ @ a8aec0c + committed PNGs (reference only)
```

Dependency direction: `experiments → controllers → predictors → physics`;
`constraints` guards every action; `workloads/sensors` feed `experiments`;
`viz` reads manifests only. Physics never imports controllers (no cycles).

## 3. Phased implementation roadmap

### P1 — Harness & invariants (1–2 wks)
- Freeze `legacy/`; pin deps + Python floor; per-component RNGs; run-manifest schema.
- Implement `constraints/` (SLO table, conservation checker) + `experiments/` trial runner.
- *Accept:* E-01 reproduces legacy direction-of-effect; substitution-rate instrumentation live;
  figures write to untracked `results/` (R-06 closed); ≥1 unit test per physics invariant.

### P2 — Physics & metrics honesty (1–2 wks)
- E-05 battery; inlet/HVAC/cooling fixes (floors, counting rule doc, no-clip probe mode).
- E-10 metric repair (dose, absolute water, work-based throughput); single `Metrics` package.
- *Accept:* E-05a–e pass with recorded tolerances; legacy numbers restated under repaired metrics.

### P3 — Fair comparisons (2 wks)
- E-02 (seed grids), E-03 (fair harness + conserving-only variants), E-04 (held-out demand).
- Trial-level paired stats (D-08); pre-registered endpoints.
- *Accept:* ΔT_peak / cooling-rate / SLO / retention CIs over ≥10 trials; H-01–H-07 verdict
  (confirmed / bounded / refuted) published per trace.

### P4 — Predictor & optimizer proof (2 wks)
- E-06 (PBD), E-07 (Tucker ablation), E-08 (greedy vs SA vs random at equal budget).
- Promote/demote PBD + Tucker per data (D-06/D-07).
- *Accept:* each component shows pre-registered marginal gain or is demoted; SA variance bounded.

### P5 — Transfer honesty + workbench (2–3 wks)
- E-09 (ECM inside RK4 loop); rescope or retire per D-09.
- Thin workbench: scenario picker, run launcher, manifest browser, figure gallery over `viz/`.
- *Accept:* transfer claims replicate dynamically or are withdrawn; workbench runs P1–P4
  pipelines end-to-end from a clean checkout.

## 4. Requirements trace (audit → roadmap)
R-01/R-06 → P1 manifests + untracked results. R-02 → v2 module split.
R-03/E-02 → per-component RNGs + seed grids (P1/P3). R-04/C-02/D-03 → `constraints/` (P1).
C-01/D-04 → conserving fallbacks (P1/P3). P-02/P-03 → P2. A-02/A-03/A-05/A-06 → P4/P5.
H-12 doc contradiction → correct in P3 reporting pass.

## 5. Risks
- Legacy effects shrink under fair harness (likely for TATS SLO/cooling) — mitigated by
  pre-registration and component decomposition (a smaller honest effect beats a large artifact).
- No calibrated facility data — mitigated by explicit toy-model labelling (D-05c).
- SA wall-time at scale — mitigated by budget-parity tests (E-08) before any real-time claim.
