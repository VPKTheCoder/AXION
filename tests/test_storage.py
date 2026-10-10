"""Safe result storage: unique dirs, no silent overwrite, crash honesty (P1.3)."""

import pytest

from axion.experiments import storage as S


def test_create_run_dir_marks_running(tmp_path):
    run = S.create_run_dir(tmp_path, "tats", repo_root=tmp_path)
    assert run.is_dir()
    assert S.read_status(run) == "RUNNING"


def test_collision_never_silent(tmp_path):
    run = S.create_run_dir(tmp_path, "tats", repo_root=tmp_path, run_id="fixed")
    assert run.is_dir()
    with pytest.raises(S.RunCollisionError):
        S.create_run_dir(tmp_path, "tats", repo_root=tmp_path, run_id="fixed")


def test_interrupted_run_not_complete(tmp_path):
    run = S.create_run_dir(tmp_path, "axion")
    assert S.read_status(run) == "RUNNING"  # no marker swap => never complete
    S.mark_finished(run, S.STATUS_FAILED)
    assert S.read_status(run) == "FAILED"


def test_bad_terminal_status_rejected(tmp_path):
    run = S.create_run_dir(tmp_path, "ecm")
    with pytest.raises(ValueError):
        S.mark_finished(run, "RUNNING")


def test_assets_dir_refused(tmp_path):
    repo = tmp_path / "repo"
    (repo / "Assets").mkdir(parents=True)
    with pytest.raises(S.UnsafeOutputDirError):
        S.assert_safe_output_dir(repo / "Assets" / "run1", repo)
    with pytest.raises(S.UnsafeOutputDirError):
        S.assert_safe_output_dir(repo, repo)
    ok = S.assert_safe_output_dir(repo / "results" / "x", repo)
    assert ok.name == "x"


def test_artifact_hash_and_relative_paths(tmp_path):
    run = S.create_run_dir(tmp_path, "tats")
    payload = run / "raw" / "obs.txt"
    payload.parent.mkdir()
    payload.write_text("hello", encoding="utf-8")
    rec = S.artifact_record(run, payload, "raw")
    assert rec["path"] == "raw/obs.txt"
    assert rec["sha256"] == S.sha256_file(payload)
    assert len(rec["sha256"]) == 64


def test_atomic_write(tmp_path):
    target = tmp_path / "manifest.json"
    S.write_text_atomic(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
