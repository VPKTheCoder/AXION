"""Manifest creation, validation, and serialization (P1.2)."""

import json

import pytest

from axion.experiments import manifest as M

COMMIT = "a" * 40


def _base(**over):
    kw = dict(run_id="r1", experiment="tats", run_class="legacy",
              source_commit=COMMIT, working_tree_clean=True,
              python_version="3.14.2")
    kw.update(over)
    return M.create_manifest(**kw)


def test_valid_manifest_round_trip(tmp_path):
    man = _base()
    assert M.is_valid(man)
    assert M.validate(man) == []
    text = M.dumps(man)
    assert M.loads(text) == man
    assert man["config_hash"] == M.config_hash({})


def test_reproducible_config_hash():
    assert M.config_hash({"b": 1, "a": [1, 2]}) == M.config_hash({"a": [1, 2], "b": 1})


def test_invalid_status_rejected():
    man = _base(status="done")
    assert not M.is_valid(man)
    assert any("status" in e for e in M.validate(man))


def test_malformed_commit_rejected():
    for bad in ("xyz", "A" * 40, "a" * 39, "", None, 0):
        man = _base(source_commit=bad)
        assert any("source_commit" in e for e in M.validate(man)), bad


def test_missing_required_field():
    man = _base()
    del man["run_id"]
    assert any("run_id" in e for e in M.validate(man))


def test_null_vs_zero_distinguished():
    man = _base()
    man["runtime_s"] = 0  # valid zero measurement
    man["exit_code"] = 0
    assert M.is_valid(man)
    man["runtime_s"] = "zero"  # invalid: strings rejected even when falsy-sounding
    assert any("runtime_s" in e for e in M.validate(man))


def test_bad_artifacts_and_events_rejected():
    man = _base()
    man["artifacts"] = [{"path": "", "sha256": "short", "kind": "nope"}]
    man["events"] = [{"no-type": 1}]
    errors = M.validate(man)
    assert any("artifacts[0]" in e for e in errors)
    assert any("events[0]" in e for e in errors)


def test_unknown_schema_rejected():
    man = _base()
    man["schema_version"] = "2.0"
    assert any("schema_version" in e for e in M.validate(man))


def test_loads_rejects_non_object():
    with pytest.raises(ValueError):
        M.loads(json.dumps([1, 2, 3]))


def test_seed_honored_flag_preserved():
    man = _base(seed_honored=False)
    assert M.is_valid(man)
    assert man["seed_honored"] is False
