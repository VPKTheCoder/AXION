# PHASE1_BASELINE_REPORT.md — Legacy Reproduction Runs (execution outcomes, not validity claims)

> All runs used `python -m axion.experiments.runner <exp> --seed 0` (repo root,
> `PYTHONPATH=src`), snapshot-copy isolation, scrubbed `GEMINI_ARTIFACT_DIR`.
> Manifests: `results/<exp>/<run_id>/manifest.json` (all schema-valid).
> Tracked `Assets/*.png` hashes before and after all runs: identical
> (`3b92ea16…`, `ddcdd182…`, `321c7f53…`). Working tree gained only `.gitignore`
> modification + additive dirs. **A successful exit is execution success only;
> it does not validate any scientific claim (single run, autocorrelated steps,
> known invariant asymmetries — see notes).**

## 1. TATS — `20261009T125517Z_7f6f44e2` — completed, exit 0, 29.7 s

- Extracted: baseline mean peak `61.9 °C` → TATS `53.8 °C` (Δ ≈ 8.1; cf. headline 8.06);
  cooling events `465 → 0`; cooling energy `130.2 → 0.0 kJ`; water `0.072109 → 0.000000 L`.
- Legacy stdout: Welch `t=-48.620, p=0.0000` (sig), pooled `d=2.807` (large; cf. paper 2.82),
  reduction `+8.059 °C, 95% CI (+7.734, +8.385)`; SA wall `16.3±3.4 ms, max 25 ms`.
- **SLO split (executed C-02 confirmation): baseline `0.0%`, TATS `100.0%`.** Under TATS's
  all-workload scope, the baseline violates on essentially every step (Gradient in the
  rotating demand always exceeds 19.5 ms) while the candidate's guard erases all
  violations — the gap measures the guard at least as much as thermals. Restatement under
  a unified scope is deferred (E-03, D-03).
- Plot: `Assets/TATS_Simulation_Results.png` regenerated inside the run dir.

## 2. AXION — `20261009T125555Z_4caac61e` — completed, exit 0, 26.2 s

- Extracted: mean peak `61.64 → 57.99 °C` (exact headline match); Greedy `59.21 °C`
  (greedy alone captures most of the peak benefit — E-08 material);
  cooling `328 → 4` (Greedy 131); water `0.050864 → 0.000620 L` (−98.8%);
  energy `91.84 → 1.12 kJ` (−98.8%); retention Base 98.9 / Greedy 100.0 / AXION 96.4%;
  paired reduction `+3.650 °C, CI (3.487, 3.814)`.
- **PBD triggers: `0`.** Over the full canonical run including both bursts, the dual-gate
  never fired once — executed observation supporting audit hypothesis A-02
  (floor 3.70 °C/s exceeds the canonical burst slope ≈3.33 °C/s). Full PBD calibration
  (precision/recall, E-06) remains deferred; no threshold was changed in Phase 1.
- Plot: `Assets/AXION_Results.png` regenerated inside the run dir.

## 3. ECM — `20261009T125309Z_aa1617f2` — completed, exit 0, 44.6 s

- Hyperscale B: naive RMSE `5.50` → ECM K=20 `0.163 °C` (exact headline match);
  throughput naive 164 → ECM 175 W, oracle 175 W.
- Edge: naive cooling `300` → K=20 `0`; Hospital: naive 164 → ECM 226 W (+37.8% ≈ +38%);
  Research: K=20 RMSE `0.177`, at oracle parity. `stat_test`: RMSE `0.1559±0.0678 °C`,
  reliability 100%.
- Nuance for Phase 2: on Hyperscale B the *naive* arm has lower static T_peak (60.4)
  than ECM (62.6) while delivering less "throughput" — consistent with the audit's
  metric critique (C-04: mean-power throughput rewards hotter schedules). Evaluation
  remains in the static-model universe (E-09 deferred).
- Plot: `Assets/ECM_Phase2_Results.png` regenerated inside the run dir.

## 4. Extraction caveats (recorded in manifests as `extraction-note` events)

- Legacy stdout embeds ANSI color escapes; regexes matched regardless, but extraction is
  best-effort string parsing, not a metrics API. TATS/AXION regexes take the *last*
  summary-table match; ECM's `rmse_C` takes the last `K=20` line (Research HPC, 0.177 —
  the B-specific 0.163 is in `stdout.txt` verbatim for auditors).
- `seed_honored=False` on all three manifests: requested `--seed 0` coincides with the
  hard-coded legacy seeds, but the runner claims no seed control (legacy ignores it).
