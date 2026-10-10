"""Safe, untracked result storage for new experiment infrastructure.

Rules enforced here (Phase 1 work package P1.3):

* New runs live under a configurable root (default ``results/``), never under
  tracked ``Assets/`` or any other tracked path.
* Each run gets a unique directory; an existing directory is never reused or
  silently overwritten (:class:`RunCollisionError`).
* A run starts life marked ``RUNNING``; only an explicit :func:`mark_finished`
  transition moves it to ``COMPLETED`` / ``FAILED`` / ``PARTIAL``. An
  interrupted run therefore still reads ``RUNNING`` and can never be mistaken
  for complete.
* The manifest is stored alongside artifacts; raw observations, derived
  summaries, plots, and logs use distinct artifact ``kind`` labels.
* Artifact paths recorded in manifests are relative to the run directory.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_PARTIAL = "PARTIAL"

# Tracked output locations that new runs must never write to (relative to repo root).
FORBIDDEN_RELATIVE_DIRS = ("Assets",)


class RunCollisionError(FileExistsError):
    """Raised when a run directory already exists (never overwrite silently)."""


class UnsafeOutputDirError(ValueError):
    """Raised when a requested output directory targets tracked artifacts."""


def utc_stamp() -> str:
    """UTC timestamp suitable for directory names (no spaces/colons)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_root(repo_root: str | Path) -> Path:
    """Default untracked results root for a repository checkout."""
    return Path(repo_root) / "results"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def assert_safe_output_dir(out_dir: str | Path, repo_root: str | Path) -> Path:
    """Validate a run directory; raise :class:`UnsafeOutputDirError` if unsafe.

    Unsafe means: inside any tracked output directory (``Assets/``), or equal
    to the repository root itself. The check is purely lexical (no I/O), so it
    can gate directory creation.
    """
    repo = Path(repo_root).resolve()
    target = Path(out_dir).resolve()
    if target == repo:
        raise UnsafeOutputDirError(f"refusing to use repository root as run dir: {target}")
    for rel in FORBIDDEN_RELATIVE_DIRS:
        if _is_within(target, repo / rel):
            raise UnsafeOutputDirError(
                f"refusing to write new results under tracked directory {rel}/: {target}"
            )
    return target


def create_run_dir(
    root: str | Path,
    experiment: str,
    *,
    repo_root: str | Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Create ``<root>/<experiment>/<utc>_<run_id>/`` with a ``RUNNING`` marker.

    Raises :class:`RunCollisionError` if the directory already exists and
    :class:`UnsafeOutputDirError` if the location targets tracked artifacts.
    """
    stamp = utc_stamp()
    rid = run_id or hashlib.sha256(stamp.encode()).hexdigest()[:8]
    run_dir = Path(root) / experiment / f"{stamp}_{rid}"
    if repo_root is not None:
        assert_safe_output_dir(run_dir, repo_root)
    if run_dir.exists():
        raise RunCollisionError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / STATUS_RUNNING).touch()
    return run_dir


def read_status(run_dir: str | Path) -> str:
    """Current lifecycle marker of a run directory (``RUNNING`` if unfinished)."""
    d = Path(run_dir)
    for name in (STATUS_COMPLETED, STATUS_FAILED, STATUS_PARTIAL, STATUS_RUNNING):
        if (d / name).exists():
            return name
    return "UNKNOWN"


def mark_finished(run_dir: str | Path, status: str) -> None:
    """Atomically transition a run from ``RUNNING`` to a terminal status."""
    if status not in (STATUS_COMPLETED, STATUS_FAILED, STATUS_PARTIAL):
        raise ValueError(f"terminal status must be COMPLETED/FAILED/PARTIAL, got {status!r}")
    d = Path(run_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {d}")
    (d / STATUS_RUNNING).unlink(missing_ok=True)
    (d / status).touch()


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file (streamed; safe for large artifacts)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(run_dir: str | Path, path: str | Path, kind: str) -> dict[str, str | None]:
    """Build a manifest artifact entry with a path relative to the run dir."""
    run = Path(run_dir)
    full = Path(path)
    try:
        rel = full.relative_to(run).as_posix()
    except ValueError:
        rel = full.as_posix()
    return {
        "path": rel,
        "sha256": sha256_file(full) if full.is_file() else None,
        "kind": kind,
    }


def write_text_atomic(path: str | Path, text: str) -> None:
    """Write text via a temporary sibling + rename (crash-safe manifest writes)."""
    target = Path(path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
