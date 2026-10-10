# AUDIT_REPOSITORY.md — Phase 0 Repository Archaeology (AXION)

> Location: `audit_phase0/` (separate from project docs; no existing file was modified).
> Source revision inspected: `a8aec0c3b201d4fcbc986cf313bf039c0b8921a9` on branch `main`
> (parent `273f0f0 Initial Project AXION release`).
> Working tree at inspection: clean (`git status`: nothing to commit).
> Audit mode: read-only. No simulation was executed (scripts were not run, because
> running them writes to `Assets/` and requires unpinned third-party packages).
> Two stdlib-only arithmetic checks were executed (ALLOWED_CAPS derivation,
> time-constant / threshold / tensor-size arithmetic); everything else is static
> inspection. Nothing below claims a simulation test "passed".

## 1. Tracked files, ignored artifacts, generated results

Tracked (`git ls-files`, 14 paths):

- `.gitignore`, `requirements.txt`, `README.md`, `Home.md`
- `Notes/Project_AXION_Explanation.md`, `Notes/Project_AXION_Research_Paper.md`
- `Scripts/core.py` (166 lines), `Scripts/tats_simulation.py` (664 lines),
  `Scripts/axion.py` (654 lines), `Scripts/ecm_simulation.py` (442 lines)
- `Assets/icon.png`, `Assets/TATS_Simulation_Results.png`,
  `Assets/ECM_Phase2_Results.png`, `Assets/AXION_Results.png`

Ignored (`.gitignore:1-6`): `__pycache__/`, `*.py[cod]`, `.pytest_cache/`,
`.mypy_cache/`, `.ruff_cache/`, `.DS_Store`. Sensible for a Python repo.

Not tracked / absent (observed fact):

- No `tests/` directory, no `test_*.py`, no `conftest.py`, no CI config
  (no `.github/`, no `tox.ini`, `pyproject.toml`, `setup.cfg`).
- No raw experiment outputs: no CSV/NPZ/JSON logs, no run manifests, no seed
  records beyond hard-coded literals in source. The only "results" are the
  three committed PNGs (677 KB, 573 KB, 686 KB) plus narrative numbers in
  `README.md:140-177` and `Notes/`.
- No dependency lock: `requirements.txt:1-4` lists `matplotlib numpy scipy
  tensorly` with no version pins and no Python version.

## 2. Entry points, imports, data flow

Entry points (all three write into `Assets/` on execution — see Finding R-06):

- `Scripts/tats_simulation.py:662-664` — `run() → summarise() → plot()`; writes
  `Assets/TATS_Simulation_Results.png` (`tats_simulation.py:653-659`, `os.makedirs(exist_ok=True)`).
- `Scripts/axion.py:650-654` — `run() → summarise() → plot()`; writes
  `Assets/AXION_Results.png` (`axion.py:640-646`).
- `Scripts/ecm_simulation.py:417-442` — `run() → stat_test() → rmse_curves() → plot()`;
  writes `Assets/ECM_Phase2_Results.png` and optionally `$GEMINI_ARTIFACT_DIR/` copy
  (`ecm_simulation.py:399-414`).

Import relationships (observed):

- All three simulations do `from core import *` plus explicit re-imports
  (`tats_simulation.py:25-26`, `axion.py:95-96`, `ecm_simulation.py:61-62`).
  Wildcard import of a module that defines `N`, `W_DIM`, `W_POW`, `demand`,
  `ThermalPhysics`, `CFG`, etc. makes name provenance fragile (improvement opportunity).
- `Scripts/core.py` is the single shared-truth module: `CFG` dict (`core.py:13-50`),
  derived globals (`N, W_DIM, W_POW, W_LAT, RACK_OF, CAPS, HVACS, ALLOWED_CAPS`,
  `core.py:52-67`), resistance network builders (`core.py:69-89`), `ThermalPhysics`
  (`core.py:94-157`), and `demand()` (`core.py:162-166`).

Data flow between subsystems:

- Thermal model → predictors/controllers: `ThermalPhysics.T` (state),
  `read_sensors()` (TATS only), `rack_inlet()` / `rack_inlet_vec()` duplicates.
- Predictors → controllers: TATS `SimulatedAnnealer._predict()` (three-source blend);
  AXION `predict()` (linearised physics + optional Tucker hook, normally `None`);
  ECM `ECM.fit()` → `LightTATS.schedule()`.
- Controllers → reporting: bespoke `Metrics` classes in `tats_simulation.py:346-382`
  and `axion.py:329-377` (different definitions, same name — confusion risk);
  ECM evaluates inline dicts (`ecm_simulation.py:162-176`).
- Reporting → plots: three independent matplotlib implementations (~100 lines each),
  no shared plotting library.

## 3. Shared mutable state

| State | Location | Risk |
|---|---|---|
| `CFG` global dict | `core.py:13-50` | Single config source (good), but unvalidated, untyped, no schema; magic numbers inline |
| `_R_MAT`, `_INV_R`, `_R_EFF`, `_TAU_EFF`, `_EI/_EJ/_EW` module globals | `core.py:80-89` | Precomputed once (good for speed); silently shared by all physics instances |
| `ThermalPhysics.T`, `.cooling_on`, `.cooling_events`, `.cooling_energy_J`, `.assignment` | `core.py:95-106` | Per-instance (good); but `assignment` only maintained via `step_assignment` path |
| `TATSScheduler.asgn / _sa_asgn` | `tats_simulation.py:269-271` | Persisted SA result between periods (intended [C1-FIX]); fallback path overwrites |
| `AxionController.perm/cap/hvac/P_cur/Tin_cur/T_prev/_slope_hist` | `axion.py:142-157` | Controller state spans steps; `cap` mutated by `load_balance` fallback (`axion.py:184-189`) |
| Global RNGs (`random`, `np.random`) | `tats:23`, `axion:93`, `ecm:59` | Three different hard seeds (42/123/0); SA draws from global `random`, sensor noise from global `np.random` — see R-03 |

## 4. Configuration flow

`CFG` in `core.py:13-50` holds everything: topology (32 nodes / 4 racks / 8 per rack),
horizon (600 steps, DT=1.0, SCHED_PERIOD=30), thermal constants, workload vectors,
SLO constants, SA hyper-parameters, objective weights, TATS/ECM constants. Derived
values (`ALLOWED_CAPS`, `_R_EFF`, `_TAU_EFF`, `PBD_THRESH`) are computed at import time.

- Strength: one place to change; all three simulations read the same `CFG`.
- Weaknesses: no validation (e.g. empty `ALLOWED_CAPS[5]` is legal — see Finding R-04);
  no per-experiment override (CLI args, env vars, or config files absent);
  SA/PBD/objective weights are global, so tuning one controller retunes the others.

Executed check (stdlib `python3 -c`, no repo modification): reproduced
`ALLOWED_CAPS` exactly — `[1.0,0.85]` / `[1.0]` / `[1.0,0.85,0.7,0.55]` /
`[1.0,0.85,0.7,0.55,0.4]` ×2 / `[]` for workloads 0–5. The empty set for Gradient
(index 5, 24 ms > L_MAX 19.5 ms) is real, not a misread.

## 5. Random-number usage (detail; fairness impact in AUDIT_CLAIMS.md)

- Seeding is global and per-script: `random.seed(42); np.random.seed(42)` (TATS),
  `random.seed(123); np.random.seed(123)` (AXION), `np.random.seed(0); random.seed(0)` (ECM).
- `ThermalPhysics.__init__` uses a *local* `np.random.default_rng(seed)` for
  initialization (`core.py:96-100`) — good isolation — but `read_sensors()`
  draws noise from the *global* `np.random.normal` (`core.py:153-156`).
  Consequence: TATS sensor noise is not owned by the physics instance, depends on
  global call order, and differs from AXION (which reads `phys.T` directly with no
  noise, `axion.py:411`). Sensor fidelity is therefore inconsistent across the two
  headline comparisons.
- SA stochasticity (`random.random`, `random.randint`, `random.choice`,
  `random.sample`) consumes the same global stream as any other `random` use in
  the process. Single fixed seed per script + single run (all `run()` loops use
  `seed=0` physics, `tats:427`, `axion:396-398`) means **no repeated-trials evidence
  exists** for TATS or AXION. ECM is the exception: it repeats 20–50 draws over
  observation sampling (`ecm:196`, `ecm:228`, `ecm:248`) but still fixes the global
  seed once, so trial streams are deterministic continuations, not independent replicates.

## 6. Findings

### R-01 [Confirmed issue — High] No tests, no CI, no raw data; PNGs are the only results artifact
Evidence: absence of `tests/`, `conftest.py`, CI config; `git ls-files` shows only
PNGs + narratives; no CSV/NPZ logging in any `run()` path.
Reasoning: headline numbers (8.06 °C, 465→0, 328→4, RMSE 0.163 °C, +38 %) cannot be
regenerated or checked without re-running unpinned code.
Uncertainty: low (file listing is complete).
Verification: add `tests/` with physics/optimizer unit tests; make every simulation
emit a timestamped run directory (params JSON + metrics CSV + figure). See AUDIT_EXPERIMENTS.md E-01.

### R-02 [Design limitation — High] Three scripts, three bespoke stacks; `core.py` is shared but the rest is forked
Evidence: two incompatible `Metrics` classes (`tats:346`, `axion:329`); two inlet
functions (`core.ThermalPhysics.rack_inlet` vs `axion.rack_inlet_vec:110-117`,
identical math); three plotting blocks; ECM uses a *different physics model*
(static profile, `ecm:89-94`) from the RK4 model it claims to transfer.
Reasoning: cross-script comparisons (e.g. "AXION vs TATS") are not apples-to-apples;
a fix in one path (e.g. SLO guard) does not propagate.
Verification: code-level diff of metric definitions (done in §2 above); proposed v2
module split in REVIVAL_ROADMAP.md.

### R-03 [Confirmed issue — High] RNG ownership is split; reproducibility claim is weaker than it looks
Evidence: `core.py:96` (local init RNG) vs `core.py:153-156` (global sensor noise);
per-script global seeds; single `seed=0` physics runs.
Reasoning: re-running a script reproduces *that* stream, but sensor noise, SA draws,
and ECM observation draws share global state — inserting one draw changes all
downstream results. There is no per-component `Generator` and no trial loop for TATS/AXION.
Verification: E-02 (multi-seed rerun harness with per-component RNGs). No new run
was performed in this audit.

### R-04 [Confirmed issue — Medium] `ALLOWED_CAPS[Grad] = []` is silently legal; each consumer papers over it differently
Evidence: `core.py:61-67` builds the empty set; executed stdlib check confirms `[]`.
TATS adds a post-hoc substitution guard (`tats:316-322`, maps violations to lowest-power
SLO-feasible workload); AXION exempts index 5 from `SLO_SENSITIVE` (`core.py:28`) so
Gradient gets all caps; ECM uses `SLO_OK` (= same list) to *refuse* Gradient
(`ecm:156-159`). Three semantics for one workload.
Reasoning: the "SLO guarantee" means different things per script; TATS's guard is a
work-substitution (fairness issue — see AUDIT_CLAIMS.md C-02).
Verification: unit test asserting `ALLOWED_CAPS` non-emptiness/invariants per workload class.

### R-05 [Potential issue requiring a test — Medium] `demand()` bursts embed the evaluation signal
Evidence: `core.py:162-166` — deterministic rotation `((arange(N)+step//10)%W_DIM)`
plus hard bursts `d[16:]=0` (steps 150–259) and `d[24:]=5` (steps 350–449).
Reasoning: every controller is evaluated on the same two bursts it was tuned against
(plot annotations in `tats:569`, `axion:542`); ECM's evaluator uses *different*
burst windows (`ecm:166-167`). Generalization beyond these bursts is untested.
Verification: E-04 (held-out demand traces, burst-position randomization).

### R-06 [Confirmed issue — Medium] Running any script overwrites tracked `Assets/*.png`
Evidence: `tats:653-659`, `axion:640-646`, `ecm:399-414` (`os.makedirs(exist_ok=True)` + `savefig`).
Reasoning: the "run to reproduce" instruction (`README.md:202-213`) dirties the working
tree by design; committed figures are both inputs (paper claims) and outputs.
Verification: inspect `git status` after a run (not done here to preserve read-only
stance); fix is to write figures to untracked `results/<timestamp>/` (roadmap P1).

### R-07 [Improvement opportunity — Low] Unpinned dependencies; `tensorly` required but unused by `axion.py`
Evidence: `requirements.txt:1-4`; `axion.py` never imports `tensorly`
(only `tats` and `ecm` use it); no version floors.
Reasoning: future installs may resolve to incompatible solver/plotting behavior;
minimal install for the AXION controller need not include tensorly.
Verification: `pip freeze` capture + `pip install --dry-run` matrix (environment work,
deferred to Phase 1 setup).

## 7. Subsystem retention recommendations (repository layer)

| Subsystem | Recommendation | Rationale |
|---|---|---|
| `core.CFG` dict | Retain and refactor | Right idea (single config), wrong form (untyped global). Promote to validated dataclass + per-run overrides |
| `core.ThermalPhysics` | Retain and refactor | Keep as legacy baseline engine; isolate RNG, remove global-noise path, add step-level energy ledger |
| `core.demand` | Retain and refactor | Keep as one *named* scenario; add a scenario library with held-out traces |
| Per-script `Metrics`/plotting | Replace after validation | Three divergent definitions must converge on one tested metrics package before any claim is re-issued |
| Committed PNGs | Retire after comparative testing | Keep as historical artifacts; future figures regenerate into untracked run dirs |
