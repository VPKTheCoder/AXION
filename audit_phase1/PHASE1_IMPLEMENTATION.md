# PHASE1_IMPLEMENTATION.md — What Was Built, Changed, and Decided

> Phase 1 added infrastructure only. No scientific equation, threshold, rank,
> policy, or scorer in `Scripts/` was modified. `Scripts/` files are byte-identical
> to `a8aec0c` (see `BASELINE_PRESERVATION.md`).

## 1. Changed files

- `M .gitignore` — appended `results/` (+ comment). Verified beforehand that no
  tracked path matches `results/` and `git check-ignore`/`git ls-files` afterwards.
  This is the **only** tracked-file modification in Phase 1, explicitly permitted
  by work package P1.3 ("add the necessary ignore rules only after checking…").

## 2. Added files

```text
src/axion/__init__.py                  package marker (__version__ = 1.0.0-phase1)
src/axion/config/__init__.py
src/axion/config/legacy_config.py      side-effect-free loader for Scripts/core.py;
                                       CFG serializer (numpy -> JSON types); sha256 helper
src/axion/experiments/__init__.py
src/axion/experiments/manifest.py      schema "1.0": create/validate/dumps/loads;
                                       None == unknown, never conflated with 0
src/axion/experiments/rng.py           SeedSequence-spawned per-stream generators
                                       (workload/init/sensor/optimization) + stdlib streams
src/axion/experiments/storage.py       unique run dirs, RUNNING->terminal markers,
                                       Assets/ refusal, atomic writes, artifact hashing
src/axion/experiments/runner.py        CLI + run_experiment() + summarize(); snapshot-copy
                                       subprocess isolation; file-redirect I/O; honest seeds
src/axion/constraints/__init__.py
src/axion/constraints/slo.py           tri-state SLO table (True/False/None-unresolved),
                                       check_step() PASS/FAIL/UNDETERMINED, fail-closed guarantee()
src/axion/constraints/workload_accounting.py
                                       aggregate permutation-vs-substitution checks +
                                       job-level WorkLedger (substitution never completable)
src/axion/constraints/actions.py       caps/HVAC/permutation/coverage/finite validators
src/axion/constraints/legacy_adapter.py
                                       binds validators to live Scripts/core.py values;
                                       marks Gradient unresolved (D-03); simulation-import ban
src/axion/metrics/__init__.py
src/axion/metrics/definitions.py       central metric definitions attached to manifests
src/axion/legacy/__init__.py
src/axion/legacy/snapshot.py           copy+hash-verify Scripts/ into run dirs; mismatch aborts
tests/conftest.py                      sys.path bootstrap (no installs)
tests/test_manifest.py  (10 tests)     valid/invalid/incomplete/reproducible manifests
tests/test_rng.py       (6 tests)      reproducibility, isolation, seed rejection
tests/test_storage.py   (7 tests)      uniqueness, collisions, markers, Assets refusal, hashing
tests/test_workload_accounting.py (8)  identity/perm/substitution/truncation + ledger incl. failure modes
tests/test_slo.py       (7 tests)      bound/batch/unresolved/fail-closed/mismatch/non-finite
tests/test_actions.py   (7 tests)      caps incl. empty set, HVAC, bijection, coverage, numerics
tests/test_legacy_adapter.py (7)       live-core facts: Gradient exemption (R-04 correction),
                                       unresolved SLO, import ban, combined action check
tests/test_runner.py    (7 tests)      success/failure/refusal/summary paths with stub scripts
audit_phase1/*.md                      this file + 6 companion reports
```

## 3. Module responsibilities and boundaries

- `config/legacy_config` reads legacy truth; never the simulation modules.
- `experiments/manifest` owns provenance shape; `storage` owns layout/lifecycle;
  `runner` owns execution honesty (exit codes, timeouts, `seed_honored=False`).
- `constraints/*` are pure functions over observed data — independent of any
  controller's objective (P1.4 requirement). `legacy_adapter` is the only bridge
  to legacy values, and it duplicates nothing (reads `core.py` at call time).
- `metrics/definitions` owns *meaning* of stored numbers; values come from runs.
- Dependency direction: `runner -> {manifest, rng, storage, legacy/snapshot,
  config/legacy_config, constraints/legacy_adapter, metrics/definitions}`.
  No cycles; legacy `Scripts/` is a data/execution dependency only.

## 4. Design decisions (with rationale)

1. **Snapshot-copy isolation over output-dir arguments.** Legacy scripts accept no
   arguments and hard-code `Assets/` from `__file__`; adding an argument would change
   scientific-adjacent code. Copies exploit `__file__`-relative outputs without touching
   a single legacy line; hash verification makes "identical code" checkable, not assumed.
2. **`seed_honored=False` instead of seed plumbing.** Wiring seeds into legacy globals
   would silently change historical outputs. The runner records the request and the
   limitation; seed grids are deferred to Phase 2 where RNG ownership is redesigned.
3. **Tri-state SLO (`None` = unresolved) instead of picking D-03 early.** Both candidate
   semantics (bound vs exempt) exist in the codebase; choosing one in Phase 1 would be a
   scientific change. The validator fails closed (`UNDETERMINED` ⇒ no guarantee).
4. **Aggregate + ledger work accounting.** Legacy exposes no job identities, so the
   strongest honest check today is multiset conservation; the ledger stands ready for v2
   controllers. Substitution is a first-class recorded event, never completion.
5. **File-redirect subprocess I/O.** Pipes hit sandbox handle-inheritance flakiness
   (WinError 5/6); files fixed it, and streaming to `stdout.txt` additionally preserves
   partial logs on timeout and bounds memory on long runs.
6. **No `pyproject.toml`, no packaging, no framework.** stdlib JSON + numpy (already a
   project dep) + pytest (already installed). Smallest coherent setup per instructions.
7. **`.gitignore` is the only tracked edit.** Everything else is additive, so the legacy
   baseline stays byte-recoverable from git at `a8aec0c`.
