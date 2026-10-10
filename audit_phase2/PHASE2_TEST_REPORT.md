# PHASE2_TEST_REPORT.md — Executed Results (97 tests; every claim from execution)

> Environment: Python 3.14.2, numpy 2.5.1, scipy 1.18.0, matplotlib 3.11.1,
> tensorly 0.9.0, pytest 9.1.1, Windows. `python -m pytest tests/ -q`:
> **97 passed** (two consecutive full-suite passes: 97, 97). Phase 1 baseline
> re-established first (59/59 after one transient sandbox-flake run — the known
> WinError pipe issue; file-redirect paths unaffected).

## New suites (38 tests, all passing)

| Suite | Tests | Key executed outcomes |
|---|---|---|
| `test_physics_equations` | 7 | replica == legacy < 5e-6 (uniform + nonuniform); inlet exact; τ=13.05 s; equilibrium zero-derivative; antisymmetry; bypass slope |
| `test_thermal_verification` | 6 | A 9.7e-13; B max 2.3e-6; C 7.1e-14; D floors/ceilings; E edge-counting + −240 W pin; F orders 4.046/4.023/4.012, DOP853 6e-11 |
| `test_energy_ledger` | 6 | rel. residual 4.9e-4 @dt=1, exact 4×/halving; quiet-step `None`; clip flagged; device energy separated |
| `test_hvac_cooling` | 9 | exact HVAC offsets; sub-ambient flagged (23.5 °C @Q=0/hvac=1); sweeps; re-trip 2N; abstract-control COP; discontinuity finite |
| `test_canonical_metrics` | 9 | dose 26.0 °C·s / 2 crossings / durations on known series; retention `None` on empty; compliance 90/95; proxy pct 98.78; zero-baseline `None` |
| `test_actions` (+1) | 8 | numpy-integer regression pin (bool still rejected) |

## Failures met and resolved (none outstanding, none hidden)

1. Replica-vs-legacy 1.26e-6 gap → root-caused to legacy float32 output cast
   (`core.py:139`), bound set to float32 rounding with comment (not relaxed blindly).
2. Batch-SLO `None` bug and stub-plot `KeyError` (new-code bugs, fixed; reported in
   Phase 1, re-verified here as passing).
3. `ALLOWED_CAPS[5]` audit-assumption refuted → mechanism corrected, pinned by test.
4. numpy-integer rejection in validators → fixed via `numbers.Integral`, regression-tested.
5. Float-cancellation in bypass-slope test → `pytest.approx` with documented reason.

## Experiment runs (all exit 0, manifests valid)

- Verification battery: `results/phase2/verification_report.json` (`all_pass: true`, 1.7 s).
- Reconciliation: 3 safe-runner runs (40.4 / 26.2 / 52.4 s) + `results/phase2/reconciliation.json`.
- Tracked figures untouched (hashes verified pre/post).
