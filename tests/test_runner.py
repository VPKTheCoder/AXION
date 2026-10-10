"""Runner behavior with fast synthetic scripts (P1.5); legacy runs are separate.

Uses tiny stub experiments injected via monkeypatched snapshot/experiment maps
so unit tests never run long simulations. Real legacy smoke runs are recorded
in audit_phase1/PHASE1_BASELINE_REPORT.md, not asserted here.
"""

import json
import subprocess
import sys

import pytest

from axion.experiments import manifest as M
from axion.experiments import runner as R
from axion.experiments import storage as S


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    scripts = repo / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "core.py").write_text(
        "CFG = {'N_NODES': 2, 'N_RACKS': 1, 'N_WORKLOADS': 2, 'SIM_STEPS': 1,\n"
        " 'SCHED_PERIOD': 1, 'L_MAX': 19.5, 'POWER_CAP_LEVELS': [1.0],\n"
        " 'HVAC_LEVELS': [0], 'WORKLOAD_NAMES': ['A', 'B']}\n"
        "N = 2\nW_DIM = 2\n"
        "import numpy as np\n"
        "W_POW = np.array([1.0, 2.0])\nW_LAT = np.array([1.0, 2.0])\n"
        "ALLOWED_CAPS = [[1.0], [1.0]]\n",
        encoding="utf-8")
    monkeypatch.setattr(R, "REPO_ROOT", repo)
    monkeypatch.setattr(R, "EXPERIMENT_SCRIPT", {"stub": "stub.py"})
    monkeypatch.setattr(R, "_EXTRACT", {})
    monkeypatch.setattr(R, "git_info", lambda _repo: ("f" * 40, True))
    return repo


def _install_stub(monkeypatch, body):
    import axion.legacy.snapshot as snap

    def _fake_snapshot(scripts_dir, dest_dir):
        from pathlib import Path
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(Path(scripts_dir) / "core.py", dest / "core.py")
        (dest / "stub.py").write_text(body, encoding="utf-8")
        return [{"file": "core.py", "sha256": "0" * 64},
                {"file": "stub.py", "sha256": "1" * 64}]

    monkeypatch.setattr(snap, "snapshot_legacy", _fake_snapshot)
    monkeypatch.setattr(R, "snapshot_legacy", _fake_snapshot)


def test_success_run_records_manifest(tmp_path, fake_repo, monkeypatch):
    _install_stub(monkeypatch, "print('Mean peak temp  Base:10.0  TATS:9.0')\n")
    man = R.run_experiment("stub", seed=0, root=tmp_path / "results",
                           repo_root=fake_repo, timeout_s=120)
    assert man["status"] == "completed"
    assert man["seed_honored"] is False
    assert man["exit_code"] == 0
    assert man["runtime_s"] is not None and man["runtime_s"] >= 0
    assert M.is_valid(man), M.validate(man)
    run_dir = tmp_path / "results" / "stub" / man["run_id"]
    assert (run_dir / "COMPLETED").exists()
    assert not (run_dir / "RUNNING").exists()
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "stdout.txt").is_file()


def test_failed_run_marked_failed(tmp_path, fake_repo, monkeypatch):
    _install_stub(monkeypatch, "import sys; print('boom', file=sys.stderr); sys.exit(3)\n")
    man = R.run_experiment("stub", seed=1, root=tmp_path / "results",
                           repo_root=fake_repo, timeout_s=120)
    assert man["status"] == "failed"
    assert man["exit_code"] == 3
    assert "exit code 3" in (man["error"] or "")
    run_dir = tmp_path / "results" / "stub" / man["run_id"]
    assert (run_dir / "FAILED").exists()


def test_unknown_experiment_rejected_before_execution(tmp_path, fake_repo):
    with pytest.raises(ValueError):
        R.run_experiment("nope", root=tmp_path / "results", repo_root=fake_repo)
    root = tmp_path / "results"
    assert not root.exists() or not any(root.iterdir())


def test_assets_output_refused(tmp_path, fake_repo, monkeypatch):
    _install_stub(monkeypatch, "print('hi')\n")
    assets_root = fake_repo / "Assets"
    with pytest.raises(S.UnsafeOutputDirError):
        R.run_experiment("stub", root=assets_root, repo_root=fake_repo)


def test_summarize_lists_runs(tmp_path, fake_repo, monkeypatch):
    _install_stub(monkeypatch, "print('hi')\n")
    man = R.run_experiment("stub", seed=0, root=tmp_path / "results",
                           repo_root=fake_repo, timeout_s=120)
    rows = R.summarize(tmp_path / "results")
    assert len(rows) == 1
    assert rows[0]["run_id"] == man["run_id"]
    assert rows[0]["manifest_valid"] is True


def test_git_info_outside_repo(tmp_path):
    with pytest.raises(RuntimeError):
        R.git_info(tmp_path)


def test_extract_metrics_best_effort():
    metrics, notes = R.extract_metrics("tats", "no numbers here")
    assert metrics == {} and notes
