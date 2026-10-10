# BASELINE_PRESERVATION.md — P1.1 Legacy Baseline Record (AXION Phase 1)

> Status: executed record. Source revision `a8aec0c3b201d4fcbc986cf313bf039c0b8921a9`
> on branch `main`. No legacy file was modified; the only tracked-file change in
> Phase 1 is an appended `results/` line in `.gitignore` (verified to hide no
> tracked path). No commit or push was made.

## 1. Source revision and working-tree state

- Commit: `a8aec0c3b201d4fcbc986cf313bf039c0b8921a9` ("Expand README with research overview").
- Parent: `273f0f0` ("Initial Project AXION release"). Branch: `main`, in sync with `origin/main`.
- Working tree at Phase 1 start: clean (`git status`: nothing to commit).
- Working tree at Phase 1 end: `M .gitignore` only; untracked additions `src/`, `tests/`,
  `audit_phase0/`, `audit_phase1/`, `results/` (ignored). `Scripts/`, `Assets/`,
  `Notes/`, `README.md`, `Home.md`, `requirements.txt`, `audit_phase0/` byte-identical
  to the inspected revision (verified: `git diff --name-only` lists only `.gitignore`;
  `git status --porcelain` shows no other `M` entries).

## 2. Tracked-file inventory (14 files, `git ls-files`)

`.gitignore`, `requirements.txt`, `README.md`, `Home.md`,
`Notes/Project_AXION_Explanation.md`, `Notes/Project_AXION_Research_Paper.md`,
`Scripts/core.py` (166 lines), `Scripts/tats_simulation.py` (664 lines),
`Scripts/axion.py` (654 lines), `Scripts/ecm_simulation.py` (442 lines),
`Assets/icon.png`, `Assets/TATS_Simulation_Results.png`,
`Assets/ECM_Phase2_Results.png`, `Assets/AXION_Results.png`.
No `tests/`, no CI config, no run manifests, no raw-data artifacts existed before Phase 1.

## 3. SHA-256 source hashes (recorded 2026-10-09, executed)

| File | SHA-256 |
|---|---|
| `Scripts/core.py` | `11ba9f4e…59fdc9bb` |
| `Scripts/tats_simulation.py` | `c5ed3fd7…f2faed` |
| `Scripts/axion.py` | `6db65ffe…c8ded6` |
| `Scripts/ecm_simulation.py` | `22713c1a…cbaf463` |
| `requirements.txt` | `64a6e8f4…232d56b` |
| `.gitignore` (pre-Phase-1) | `d65300fa…ed3d70` |
| `README.md` | `f627d4f5…d727523` |
| `Home.md` | `e54e8dfe…b14989526` |
| `Notes/Project_AXION_Explanation.md` | `fd08122d…2906b36a41f` |
| `Notes/Project_AXION_Research_Paper.md` | `01a3cc52…c4915b5c3de5` |
| `Assets/TATS_Simulation_Results.png` | `3b92ea16…dce5f08` |
| `Assets/ECM_Phase2_Results.png` | `321c7f53…d5720` |
| `Assets/AXION_Results.png` | `ddcdd182…5494b5` |
| `Assets/icon.png` | `c0e4a976…930a93` |

(Full digests in `results/*/legacy_snapshot` manifests and the Phase 1 shell transcript;
prefixes above disambiguate. Recompute with
`python3 -c "import hashlib;print(hashlib.sha256(open(F,'rb').read()).hexdigest())"`.)

## 4. Environment: original (unknown) vs current (observed, executed)

- Original environment: **not recorded in the repo** — no Python version, no `pip freeze`,
  no platform note beyond banner strings ("HP 15-hr1000TU · Core Ultra 5 125H · 16 GB DDR5").
  `requirements.txt` pins nothing (`matplotlib numpy scipy tensorly`).
- Current environment (executed `python3 -c "import …"` + `pip list`):
  Python `3.14.2` (MSC v.1944 AMD64, Windows), numpy `2.5.1`, scipy `1.18.0`,
  matplotlib `3.11.1`, tensorly `0.9.0`, pytest `9.1.1`.
- Difference: clean-checkout reproduction is documented *for this environment only*
  (procedure in §6). Numerical identity with the author's machine is **not claimed**;
  unpinned BLAS/LAPACK and library versions may shift solver trajectories. The smoke
  runs (§7, `PHASE1_BASELINE_REPORT.md`) reproduce all headline magnitudes, which bounds
  this risk for the three canonical runs but does not eliminate it.

## 5. Legacy execution commands (verified by execution)

From the repository root with `src/` importable (Phase 1 runner sets this up):

```bash
python Scripts/tats_simulation.py   # TATS — MUST NOT run in place (overwrites Assets/)
python Scripts/axion.py             # AXION controller — same warning
python Scripts/ecm_simulation.py    # ECM — same warning (+$GEMINI_ARTIFACT_DIR second copy)
```

Safe Phase 1 equivalents (byte-verified snapshot copies in untracked run dirs):

```bash
$env:PYTHONPATH='src'
python -m axion.experiments.runner tats  --seed 0
python -m axion.experiments.runner axion --seed 0
python -m axion.experiments.runner ecm   --seed 0
python -m axion.experiments.runner --summary results
```

## 6. Output paths and platform assumptions

- Each script derives its figure path from `__file__`:
  `tats_simulation.py:653-659`, `axion.py:640-646` (`os.makedirs(exist_ok=True)` +
  `savefig` into `<repo>/Assets/`), `ecm_simulation.py:399-414` (same + optional
  `$GEMINI_ARTIFACT_DIR` copy). **In-place execution overwrites tracked figures by design.**
- The runner's redirection strategy exploits exactly this: snapshot copies carry their own
  `__file__`, so outputs land in `<run>/Assets/`. Copies are SHA-256-verified before
  execution (`axion/legacy/snapshot.py`); mismatch aborts the run.
- Platform notes: scripts force `sys.stdout.reconfigure(encoding="utf-8")` (`core.py:5-8`);
  matplotlib uses the `Agg` backend (headless-safe); stdout contains ANSI color escapes
  (parsing caveat recorded in `PHASE1_BASELINE_REPORT.md`); console is Windows
  (`win32`, PowerShell) in this environment — line endings/encodings had no observed effect.
- Missing dependencies: none in this environment (all four install requirements present).
  On a bare machine: `pip install -r requirements.txt` + pytest for the new suite.
  Legacy scripts ignore CLI arguments and environment seeds (blocker for seed grids — §8).

## 7. Execution blockers found (and resolutions)

| Blocker | Severity | Resolution in Phase 1 |
|---|---|---|
| In-place run overwrites tracked `Assets/*.png` (R-06) | High | Snapshot-copy subprocess isolation; verified by pre/post hashes (identical) |
| Legacy scripts ignore requested seeds (hard-coded `random.seed` + physics `seed=0`) | Medium | Recorded honestly (`seed_honored=False`); seed-grid experiments deferred to Phase 2 (no silent global rewiring) |
| `GEMINI_ARTIFACT_DIR` env would duplicate ECM output outside the run dir | Low | Scrubbed from child env; recorded in manifest notes |
| Python-subprocess pipe-handle flakiness in this sandbox (WinError 5/6) | Medium | File-redirect execution (`_spawn`/`_capture_short`); 3 consecutive clean 59/59 suite passes afterwards (see `PHASE1_TEST_REPORT.md`) |

## 8. Discrepancies between Phase 0 audit assumptions and observed code facts

1. **R-04 corrected (material).** The audit's stdlib re-derivation assumed Gradient was
   SLO-bound and stated `ALLOWED_CAPS[5] == []`. Executed import of the real `core.py`
   (`tests/test_legacy_adapter.py::test_gradient_cap_exemption_reproduced`, passing)
   shows the opposite: Gradient is *exempt* from `SLO_SENSITIVE`, so
   `ALLOWED_CAPS[5] == [1.0, 0.85, 0.70, 0.55, 0.40]` — a 24 ms workload may legally run
   at cap 0.40 (L_eff = 60 ms) under AXION's scope. The three-way inconsistency stands
   with corrected mechanism: TATS's SA objective (`W_LAT.max() > L_MAX → inf`,
   `tats_simulation.py:205-207`) and TATS/ECM scorers treat Gradient as bound, while
   core caps + AXION's scorer exempt it. `audit_phase0/` is left intact per instructions;
   this correction is pinned by a passing test and referenced from `PHASE1_DEFERRED_WORK.md` (D-03).
2. **Environment assumption resolved.** The audit recorded "unpinned/unknown" deps;
   this document records the actual installed versions (§4).
3. **No other audit code-fact was refuted.** TATS fallback substitution (C-01), PBD
   dual-gate (A-02), sensor-noise global RNG (R-03), and counting-rule differences were
   all consistent with the executed runs (notably: AXION PBD triggers = 0 over the full
   canonical run — see `PHASE1_BASELINE_REPORT.md`).
