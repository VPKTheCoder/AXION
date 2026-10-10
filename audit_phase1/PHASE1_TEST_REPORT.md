# PHASE1_TEST_REPORT.md — Executed Results (no unexecuted test is reported as passing)

> Environment: Python 3.14.2, numpy 2.5.1, scipy 1.18.0, matplotlib 3.11.1,
> tensorly 0.9.0, pytest 9.1.1, Windows (win32). Command: `python -m pytest tests/ -q`.
> Full suite uses small synthetic inputs only; no test runs a long simulation.

## 1. Results

| Run | Result |
|---|---|
| Suite pass 1 (after file-redirect fix) | **59 passed** |
| Suite pass 2 (stability re-run) | **59 passed** |
| Suite pass 3 (stability re-run) | **59 passed** |

Three consecutive clean passes. Coverage by file: `test_manifest` 10, `test_rng` 6,
`test_storage` 7, `test_workload_accounting` 8, `test_slo` 7, `test_actions` 7,
`test_legacy_adapter` 7, `test_runner` 7 — total 59 (includes regression pins for
R-04-corrected Gradient exemption, C-01 substitution detection, D-03 unresolved SLO).

## 2. Failures encountered during development (all fixed, none outstanding)

1. `test_batch_workload_unbounded` — bug in new code: `WorkloadSLO.allows()` returned
   `None` for batch workloads (threshold `None` short-circuited before the batch check).
   Fixed (`slo.py`): batch returns `True`; `None` reserved for genuinely unresolved
   applicability. Test now passes.
2. `KeyError: 'stub'` in runner — expected-plot lookup assumed a legacy experiment.
   Fixed: `.get(experiment)` with plot check only for known experiments. Tests pass.
3. `test_empty_gradient_allowed_set_reproduced` — **audit assumption refuted by code**:
   `ALLOWED_CAPS[5]` is the full list (exemption), not `[]`. Test rewritten to pin the
   true facts; correction documented in `BASELINE_PRESERVATION.md` §8. This is the
   intended behavior of the audit instruction ("verify before treating as confirmed").
4. Intermittent `OSError: [WinError 5/6]` in pipe-based subprocess spawning (sandbox
   handle-inheritance flakiness; identical commands alternated fail/pass across runs).
   Fixed by file-redirect execution (`_spawn`/`_capture_short` in `runner.py`) — a
   strict robustness improvement that also preserves partial logs on timeout. Three
   consecutive 59/59 passes after the change. No test was weakened to obtain passes
   (the tautological stream-isolation assertion found during review was rewritten as a
   real independence check before the fix).

## 3. Could-not-run / not-applicable

- Full seed grids, statistical comparisons, optimizer ablations: **not run** (out of
  scope for Phase 1 by design; legacy scripts ignore seed inputs — see
  `PHASE1_DEFERRED_WORK.md`).
- No test requires network, GPU, or the author's original laptop; none was skipped.
- `test_git_info_outside_repo` asserts `RuntimeError` for non-repos — passes; real-repo
  `git_info` is additionally exercised by all three smoke runs (manifests record the
  true commit `a8aec0c…` and dirty state).
