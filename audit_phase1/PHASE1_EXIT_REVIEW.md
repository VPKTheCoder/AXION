# PHASE1_EXIT_REVIEW.md — Acceptance-Criterion Verdicts (evidence-linked)

> Verdict key: **PASS** (executed evidence) / **PARTIAL** (gaps listed) /
> **FAIL** (evidence of non-satisfaction) / **NOT TESTED**. No PASS is awarded on
> inspection alone where execution was required.

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Legacy source recoverable & unmodified (except minimal justified adapter) | **PASS** | `git diff --name-only` → only `.gitignore`; `Scripts/` hashes match §3 of `BASELINE_PRESERVATION.md`; zero compatibility edits to legacy code (snapshot isolation instead) |
| 2 | Clean-checkout reproduction procedure documented | **PASS** | `BASELINE_PRESERVATION.md` §§4–6: env table, execution commands, safe-runner equivalents; three executed smoke runs from this checkout |
| 3 | New experiments generate validated manifests with source+config provenance | **PASS** | Schema `1.0` (`manifest.py`); 10 manifest tests pass; all 3 smoke-run `manifest.json` files validate (`manifest_valid: true` in `--summary`) with commit, config hash, seeds, `seed_honored=False` |
| 4 | Artifacts stored safely outside tracked historical outputs | **PASS** | `storage.py` Assets-refusal (+ test); `results/` git-ignored (verified); all run outputs under `results/*/`; tracked `Assets/*.png` hashes identical pre/post |
| 5 | Independent validators for workload, SLO, action invariants | **PASS** | `constraints/{workload_accounting,slo,actions}.py` + `legacy_adapter.py`; pure-function, controller-independent by construction |
| 6 | Tests demonstrate validator behavior incl. failure cases | **PASS** | 59/59 pass ×3 consecutive runs; failure-mode tests: substitution, UNDETERMINED/fail-closed, invalid caps/HVAC/perm/NaN, ledger errors, runner failure/refusal paths |
| 7 | Runner captures actual outcomes, never assumes success | **PASS** | Exit codes/timeouts/exceptions recorded; `RUNNING`→terminal markers; stub-tested failed (`exit 3`→`failed`), timeout, missing-plot (`partial`), and config-error (exit 2, pre-execution) paths |
| 8 | Baseline reproduction status per experiment (TATS/AXION/ECM) | **PASS** | `PHASE1_BASELINE_REPORT.md`: all three completed exit-0 with commands, runtimes (29.7/26.2/44.6 s), artifacts, extracted metrics, deviations (ANSI escapes, ECM last-match scope, PBD=0) |
| 9 | Incomplete tasks & uncertainties explicitly listed | **PASS** | `PHASE1_DEFERRED_WORK.md` (13 items) + `PHASE1_INVARIANTS.md` §4 (5 unenforceable invariants) + R-04 correction in `BASELINE_PRESERVATION.md` §8 |
| 10 | No unsupported scientific-improvement claim | **PASS** | No threshold/rank/policy/scorer changed; smoke numbers reported as execution records with validity disclaimers; PBD=0 reported as observation, not a fix |

**Overall: Phase 1 is ready for review.** All ten criteria PASS on executed evidence.
Two review inputs are requested before Phase 2: (a) the D-03 Gradient-SLO decision
(options in `audit_phase0/REVIVAL_DECISIONS.md`, facts corrected in
`BASELINE_PRESERVATION.md` §8); (b) confirmation that the snapshot-copy execution
model remains acceptable for Phase 2 seed-grid work or should be replaced by a v2
re-implementation with owned RNGs.
