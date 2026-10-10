"""Versioned experiment-manifest schema, creation, validation, and I/O.

Schema version ``"1.0"``. JSON serialization only (standard library).
Unknown/unavailable values are recorded as ``None`` and are always
distinguishable from valid zero-valued measurements (``0``, ``0.0``,
``""``, ``[]``, ``{}``), which validators must accept.

Nothing here is imported by legacy code; legacy scripts cannot produce
manifests themselves. The runner (:mod:`axion.experiments.runner`) builds
manifests around legacy subprocess execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"

RUN_CLASSES = ("legacy", "exploratory", "registered_comparison")
STATUSES = ("running", "completed", "failed", "partial")
ARTIFACT_KINDS = ("raw", "derived", "plot", "log", "manifest", "snapshot", "other")

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_REQUIRED: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "experiment",
    "run_class",
    "source_commit",
    "working_tree_clean",
    "python_version",
    "status",
)


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def config_hash(config: dict[str, Any]) -> str:
    """Deterministic SHA-256 over canonical JSON of a config mapping."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_manifest(
    *,
    run_id: str,
    experiment: str,
    run_class: str,
    source_commit: str,
    working_tree_clean: bool,
    python_version: str,
    dependency_versions: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
    scenario_id: str | None = None,
    workload_trace_hash: str | None = None,
    controller_id: str | None = None,
    predictor_id: str | None = None,
    root_seed: int | None = None,
    subsystem_seeds: dict[str, int] | None = None,
    seed_honored: bool | None = None,
    status: str = "running",
    notes: str = "",
) -> dict[str, Any]:
    """Build a new manifest with explicit unknowns as ``None``.

    ``seed_honored=False`` records that the executed code ignores the
    requested seed (true for legacy scripts with hard-coded seeds); it must
    never be silently upgraded to ``True``.
    """
    cfg = dict(config) if config else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "experiment": experiment,
        "run_class": run_class,
        "source_commit": source_commit,
        "working_tree_clean": working_tree_clean,
        "python_version": python_version,
        "dependency_versions": dict(dependency_versions) if dependency_versions else None,
        "config": cfg,
        "config_hash": config_hash(cfg),
        "scenario_id": scenario_id,
        "workload_trace_hash": workload_trace_hash,
        "controller_id": controller_id,
        "predictor_id": predictor_id,
        "root_seed": root_seed,
        "subsystem_seeds": dict(subsystem_seeds) if subsystem_seeds else None,
        "seed_honored": seed_honored,
        "started_utc": utcnow_iso(),
        "finished_utc": None,
        "status": status,
        "exit_code": None,
        "error": None,
        "runtime_s": None,
        "output_dir": None,
        "artifacts": [],
        "metrics": {},
        "metric_definitions": {},
        "events": [],
        "notes": notes,
    }


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(manifest: dict[str, Any]) -> list[str]:
    """Validate a manifest mapping; return a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]

    for key in _REQUIRED:
        if key not in manifest:
            errors.append(f"missing required field: {key}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {manifest.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION!r})"
        )
    if not isinstance(manifest.get("run_id"), str) or not manifest["run_id"]:
        errors.append("run_id must be a non-empty string")
    if not isinstance(manifest.get("experiment"), str) or not manifest["experiment"]:
        errors.append("experiment must be a non-empty string")
    if manifest.get("run_class") not in RUN_CLASSES:
        errors.append(f"run_class must be one of {RUN_CLASSES}")
    commit = manifest.get("source_commit")
    if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
        errors.append("source_commit must be a 40-char lowercase hex git hash")
    if not isinstance(manifest.get("working_tree_clean"), bool):
        errors.append("working_tree_clean must be a boolean")
    if not isinstance(manifest.get("python_version"), str) or not manifest["python_version"]:
        errors.append("python_version must be a non-empty string")
    if manifest.get("status") not in STATUSES:
        errors.append(f"status must be one of {STATUSES}")

    dep = manifest.get("dependency_versions")
    if dep is not None and not isinstance(dep, dict):
        errors.append("dependency_versions must be an object or null")
    cfg = manifest.get("config")
    if "config" in manifest and not isinstance(cfg, dict):
        errors.append("config must be an object")
    if "config_hash" in manifest and manifest.get("config_hash") is not None:
        if not isinstance(manifest["config_hash"], str):
            errors.append("config_hash must be a string or null")

    for key in ("root_seed", "exit_code"):
        val = manifest.get(key)
        if val is not None and not (isinstance(val, int) and not isinstance(val, bool)):
            errors.append(f"{key} must be an integer or null (got {val!r})")
    for key in ("scenario_id", "workload_trace_hash", "controller_id",
                "predictor_id", "error", "output_dir", "notes",
                "started_utc", "finished_utc"):
        if key in manifest and manifest[key] is not None and not isinstance(manifest[key], str):
            errors.append(f"{key} must be a string or null")
    if "seed_honored" in manifest and manifest["seed_honored"] is not None \
            and not isinstance(manifest["seed_honored"], bool):
        errors.append("seed_honored must be a boolean or null")
    if "runtime_s" in manifest and manifest["runtime_s"] is not None \
            and not _is_num(manifest["runtime_s"]):
        # 0 / 0.0 are valid measurements; only non-numerics are rejected.
        errors.append("runtime_s must be a number or null")
    if "subsystem_seeds" in manifest and manifest["subsystem_seeds"] is not None \
            and not isinstance(manifest["subsystem_seeds"], dict):
        errors.append("subsystem_seeds must be an object or null")

    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        for i, art in enumerate(artifacts):
            if not isinstance(art, dict):
                errors.append(f"artifacts[{i}] must be an object")
                continue
            if not isinstance(art.get("path"), str) or not art["path"]:
                errors.append(f"artifacts[{i}].path must be a non-empty string")
            if art.get("sha256") is not None and (
                    not isinstance(art["sha256"], str) or len(art["sha256"]) != 64):
                errors.append(f"artifacts[{i}].sha256 must be a 64-char hex string or null")
            if art.get("kind") is not None and art.get("kind") not in ARTIFACT_KINDS:
                errors.append(f"artifacts[{i}].kind must be one of {ARTIFACT_KINDS} or null")

    for key in ("metrics", "metric_definitions"):
        if key in manifest and not isinstance(manifest[key], dict):
            errors.append(f"{key} must be an object")
    events = manifest.get("events", [])
    if not isinstance(events, list):
        errors.append("events must be a list")
    else:
        for i, ev in enumerate(events):
            if not isinstance(ev, dict) or not isinstance(ev.get("type"), str):
                errors.append(f"events[{i}] must be an object with a string 'type'")

    return errors


def is_valid(manifest: dict[str, Any]) -> bool:
    """True when :func:`validate` reports no errors."""
    return not validate(manifest)


def dumps(manifest: dict[str, Any]) -> str:
    """Serialize a manifest to canonical JSON (sorted keys, 2-space indent)."""
    return json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"


def loads(text: str) -> dict[str, Any]:
    """Parse a manifest document; raises :class:`ValueError` if not a JSON object."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("manifest document must be a JSON object")
    return data
