"""Minimal command-line experiment runner (Phase 1 work package P1.5).

Capabilities:

* Select a legacy experiment (``tats`` | ``axion`` | ``ecm``), request a seed,
  choose an output root, execute, and write a validated manifest.
* Validate configuration *before* execution (unknown experiment, unsafe output
  dir, snapshot mismatch all abort without running anything).
* Record source revision + working-tree state + environment.
* Execute legacy scripts as isolated subprocesses running **byte-verified
  copies** in the run directory (so hard-coded ``Assets/`` outputs land
  inside the run dir; tracked historical figures are never touched).
* Capture stdout/stderr, exceptions, return code, and runtime; mark failed
  runs accurately; support repeated runs with explicit seeds.
* Emit a machine-readable summary of runs under a root.

Honesty rules (no fabricated reproduction):

* Legacy scripts ignore CLI seeds (hard-coded ``random.seed`` / physics
  ``seed=0``). The manifest records the requested seed with
  ``seed_honored=False`` and a note. The runner never claims seed control it
  does not have.
* Headline-metric extraction from legacy stdout is best-effort regex parsing,
  recorded under ``metrics`` with ``metric_definitions`` attached and an
  ``events`` entry describing the extraction. A successful exit is reported
  as *execution success*, never as scientific validity.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(REPO_ROOT / "src"))

from axion.config.legacy_config import load_core  # noqa: E402
from axion.constraints.legacy_adapter import legacy_config_summary  # noqa: E402
from axion.experiments import manifest as M  # noqa: E402
from axion.experiments import rng as RNG  # noqa: E402
from axion.experiments import storage as S  # noqa: E402
from axion.legacy.snapshot import (  # noqa: E402
    EXPERIMENT_SCRIPT,
    snapshot_legacy,
)
from axion.metrics.definitions import definitions_for  # noqa: E402

RUNNER_VERSION = "1.0"
DEFAULT_TIMEOUT_S = 1800

# Best-effort headline extraction patterns over legacy stdout.
_EXTRACT: dict[str, dict[str, str]] = {
    "tats": {
        "mean_peak_temp_C": r"Mean peak temp\s+Base:([0-9.]+).*\sTATS:([0-9.]+)",
        "cooling_events": r"Cooling events\s+Base:(\d+)\s+TATS:(\d+)",
    },
    "axion": {
        "mean_peak_temp_C": r"Mean peak temp\s+Base:([0-9.]+).*AXION:([0-9.]+)",
        "cooling_events": r"Cooling events\s+Base:(\d+)\s+Greedy:\d+\s+AXION:(\d+)",
        "pbd_triggers": r"PBD triggers\s+(\d+)",
    },
    "ecm": {
        "rmse_C": r"ECM K=\s*20\s+RMSE=([0-9.]+)",
    },
}


def _spawn(argv: list[str], cwd: Path, env: dict[str, str] | None,
             stdout_path: Path, stderr_path: Path,
             timeout: int | None) -> int:
    """Spawn a child streaming stdout/stderr directly into files; return exit code.

    File redirection (instead of pipes) avoids pipe-handle inheritance
    failures seen in restricted Windows sandboxes, bounds memory on long
    runs, and preserves partial logs when a timeout kills the child.
    Transient spawn :class:`OSError`s are retried; non-zero exits and
    timeouts are reported, never masked.
    """
    last: OSError | None = None
    for _ in range(3):
        try:
            with open(stdout_path, "w", encoding="utf-8") as out, \
                    open(stderr_path, "w", encoding="utf-8") as err:
                proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                        stdout=out, stderr=err)
                try:
                    return proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    raise
        except OSError as exc:
            last = exc
            time.sleep(0.5)
    raise last  # type: ignore[misc]


def _capture_short(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Capture small command output via temp files (pipe-free, sandbox-safe)."""
    import tempfile

    last: OSError | None = None
    for _ in range(3):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out_p, err_p = Path(tmp) / "o.txt", Path(tmp) / "e.txt"
                code = _spawn(argv, cwd, None, out_p, err_p, timeout=60)
                return subprocess.CompletedProcess(
                    argv, code, out_p.read_text(encoding="utf-8"),
                    err_p.read_text(encoding="utf-8"))
        except OSError as exc:
            last = exc
            time.sleep(0.5)
    raise last  # type: ignore[misc]


def git_info(repo_root: Path) -> tuple[str, bool]:
    """(commit hash, working-tree-clean). Raises RuntimeError outside a repo."""
    commit = _capture_short(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if commit.returncode != 0:
        raise RuntimeError("not a git repository: cannot record source revision")
    status = _capture_short(["git", "status", "--porcelain"], cwd=repo_root)
    dirty = bool(status.stdout.strip())
    return commit.stdout.strip(), not dirty


def dependency_versions() -> dict[str, str]:
    """Best-effort versions of relevant packages; missing ones marked explicitly."""
    out: dict[str, str] = {}
    for name in ("numpy", "scipy", "matplotlib", "tensorly"):
        try:
            mod = __import__(name)
            out[name] = str(getattr(mod, "__version__", "unknown"))
        except ImportError:
            out[name] = "NOT_INSTALLED"
    return out


def extract_metrics(experiment: str, stdout: str) -> tuple[dict[str, Any], list[str]]:
    """Regex-extract headline numbers; returns (metrics, notes). All best-effort."""
    metrics: dict[str, Any] = {}
    notes: list[str] = []
    for key, pattern in _EXTRACT.get(experiment, {}).items():
        matches = re.findall(pattern, stdout)
        if not matches:
            notes.append(f"extraction: pattern for {key} matched nothing")
            continue
        last = matches[-1]
        vals = [last] if isinstance(last, str) else list(last)
        try:
            nums = [float(v) for v in vals]
        except ValueError:
            notes.append(f"extraction: non-numeric match for {key}: {last!r}")
            continue
        if key in ("cooling_events", "mean_peak_temp_C") and len(nums) == 2:
            metrics[f"{key}_baseline"] = nums[0]
            metrics[key] = nums[1]
        elif len(nums) == 1:
            metrics[key] = nums[0]
        else:
            metrics[key] = nums
    return metrics, notes


def run_experiment(
    experiment: str,
    *,
    seed: int = 0,
    root: str | Path | None = None,
    repo_root: str | Path = REPO_ROOT,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """Execute one legacy experiment safely; return the completed manifest.

    Raises on configuration errors (unknown experiment, unsafe output dir,
    snapshot mismatch). Script failure is *recorded* (status failed), not raised.
    """
    repo = Path(repo_root)
    if experiment not in EXPERIMENT_SCRIPT:
        raise ValueError(f"unknown experiment {experiment!r}; "
                         f"expected one of {sorted(EXPERIMENT_SCRIPT)}")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed!r}")

    out_root = Path(root) if root else S.default_root(repo)
    run_dir = S.create_run_dir(out_root, experiment, repo_root=repo)

    commit, clean = git_info(repo)
    core = load_core(repo / "Scripts")
    cfg_summary = legacy_config_summary(core)
    cfg = {"legacy": cfg_summary, "requested_seed": seed,
           "runner_version": RUNNER_VERSION}
    man = M.create_manifest(
        run_id=run_dir.name, experiment=experiment, run_class="legacy",
        source_commit=commit, working_tree_clean=clean,
        python_version=sys.version.split()[0],
        dependency_versions=dependency_versions(),
        config=cfg, scenario_id="legacy-demand-core",
        controller_id=f"legacy-{experiment}", predictor_id=f"legacy-{experiment}",
        root_seed=seed, subsystem_seeds=RNG.stream_seeds(seed),
        seed_honored=False,  # legacy scripts hard-code their seeds; see notes
        notes=("Legacy scripts ignore requested seeds (hard-coded random.seed + "
               "physics seed=0). seed_honored=False. Executed byte-verified "
               "snapshot copies; tracked Assets/ untouched."),
    )
    man["output_dir"] = run_dir.name
    man["metric_definitions"] = definitions_for(experiment)
    manifest_path = run_dir / "manifest.json"
    S.write_text_atomic(manifest_path, M.dumps(man))

    script = EXPERIMENT_SCRIPT[experiment]
    t0 = time.perf_counter()
    try:
        snap_dir = run_dir / "legacy_snapshot"
        records = snapshot_legacy(repo / "Scripts", snap_dir)
        man["artifacts"].append({"path": "legacy_snapshot",
                                  "sha256": None, "kind": "snapshot"})
        for rec in records:
            man["artifacts"].append({"path": f"legacy_snapshot/{rec['file']}",
                                      "sha256": rec["sha256"], "kind": "snapshot"})
        S.write_text_atomic(manifest_path, M.dumps(man))

        env = dict(os.environ)
        env.pop("GEMINI_ARTIFACT_DIR", None)  # legacy ECM second-save path; keep runs hermetic
        stdout_path, stderr_path = run_dir / "stdout.txt", run_dir / "stderr.txt"
        try:
            returncode: int | None = _spawn(
                [python_exe or sys.executable, str(snap_dir / script)],
                run_dir, env, stdout_path, stderr_path, timeout_s)
        except subprocess.TimeoutExpired:
            man["runtime_s"] = round(time.perf_counter() - t0, 3)
            man["status"] = "failed"
            man["exit_code"] = None
            man["error"] = f"timeout after {timeout_s}s (partial logs preserved)"
            man["events"].append({"type": "timeout",
                                   "detail": f"killed after {timeout_s}s"})
            runtime = man["runtime_s"]
            proc_stdout = stdout_path.read_text(encoding="utf-8") \
                if stdout_path.is_file() else ""
            returncode = None
        else:
            runtime = time.perf_counter() - t0
            proc_stdout = stdout_path.read_text(encoding="utf-8") \
                if stdout_path.is_file() else ""
        man["runtime_s"] = round(runtime, 3)
        man["exit_code"] = returncode
        man["artifacts"].append(S.artifact_record(run_dir, run_dir / "stdout.txt", "log"))
        man["artifacts"].append(S.artifact_record(run_dir, run_dir / "stderr.txt", "log"))
        for png in sorted((run_dir / "Assets").glob("*.png")) if (run_dir / "Assets").is_dir() else []:
            man["artifacts"].append(S.artifact_record(run_dir, png, "plot"))

        metrics, notes = extract_metrics(experiment, proc_stdout)
        man["metrics"] = metrics
        for note in notes:
            man["events"].append({"type": "extraction-note", "detail": note})
        if returncode == 0:
            man["status"] = "completed"
            expected = {"tats": "TATS_Simulation_Results.png",
                        "axion": "AXION_Results.png",
                        "ecm": "ECM_Phase2_Results.png"}.get(experiment)
            if expected is not None and not (run_dir / "Assets" / expected).is_file():
                man["status"] = "partial"
                man["events"].append({"type": "missing-plot",
                                       "detail": f"exit 0 but {expected} absent"})
        elif returncode is None:
            pass  # timeout already recorded above; keep failed status
        else:
            man["status"] = "failed"
            man["error"] = f"exit code {returncode}; see stderr.txt"
            tail = (stderr_path.read_text(encoding="utf-8")
                    if stderr_path.is_file() else "")[-2000:]
            if tail.strip():
                man["events"].append({"type": "stderr-tail", "detail": tail})
    except Exception as exc:  # configuration / snapshot failures
        man["runtime_s"] = round(time.perf_counter() - t0, 3)
        man["status"] = "failed"
        man["error"] = f"{type(exc).__name__}: {exc}"
        raise  # config errors abort loudly AND are recorded below via finally-style write
    finally:
        man["finished_utc"] = M.utcnow_iso()
        S.write_text_atomic(manifest_path, M.dumps(man))
        terminal = {"completed": S.STATUS_COMPLETED, "failed": S.STATUS_FAILED,
                    "partial": S.STATUS_PARTIAL}[man["status"]]
        S.mark_finished(run_dir, terminal)

    errors = M.validate(man)
    if errors:
        man["events"].append({"type": "manifest-validation-errors", "detail": "; ".join(errors)})
        S.write_text_atomic(manifest_path, M.dumps(man))
    return man


def summarize(root: str | Path) -> list[dict[str, Any]]:
    """Machine-readable summary of every run directory under ``root``."""
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(Path(root).glob("*/*/manifest.json")):
        try:
            man = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows.append({"run_dir": str(manifest_path.parent), "manifest": "UNREADABLE"})
            continue
        rows.append({
            "run_dir": str(manifest_path.parent),
            "run_id": man.get("run_id"),
            "experiment": man.get("experiment"),
            "status": man.get("status"),
            "exit_code": man.get("exit_code"),
            "runtime_s": man.get("runtime_s"),
            "metrics": man.get("metrics", {}),
            "manifest_valid": M.is_valid(man),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AXION Phase 1 legacy experiment runner")
    parser.add_argument("experiment", nargs="?",
                        help="tats | axion | ecm (omit with --summary)")
    parser.add_argument("--seed", type=int, default=0,
                        help="requested root seed (recorded; legacy scripts ignore it)")
    parser.add_argument("--root", default=None, help="results root (default: <repo>/results)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help="per-run timeout in seconds")
    parser.add_argument("--summary", default=None,
                        help="print JSON summary of runs under ROOT and exit")
    args = parser.parse_args(argv)

    if args.summary:
        print(json.dumps(summarize(args.summary), indent=2))
        return 0
    if not args.experiment:
        parser.error("experiment is required unless --summary is given")
    try:
        man = run_experiment(args.experiment, seed=args.seed,
                             root=args.root, timeout_s=args.timeout)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"runner configuration error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"run_id": man["run_id"], "status": man["status"],
                      "exit_code": man.get("exit_code"),
                      "runtime_s": man.get("runtime_s"),
                      "metrics": man.get("metrics", {})}, indent=2))
    return 0 if man["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
