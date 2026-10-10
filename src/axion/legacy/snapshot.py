"""Snapshot helpers: copy legacy sources into a run dir, never modify them.

Phase 0 finding R-06: legacy scripts hard-code their figure output to
``<repo>/Assets/`` (computed from ``__file__``), so executing them in place
would overwrite tracked historical figures. The safe redirection strategy is
to execute *byte-identical copies* in an untracked run directory: because the
output path derives from ``__file__``, the copies write into the run dir
instead. Every copy is hash-verified against the repository original before
execution; any mismatch aborts the run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from axion.config.legacy_config import sha256_file

LEGACY_FILES: tuple[str, ...] = ("core.py", "tats_simulation.py", "axion.py", "ecm_simulation.py")

EXPERIMENT_SCRIPT: dict[str, str] = {
    "tats": "tats_simulation.py",
    "axion": "axion.py",
    "ecm": "ecm_simulation.py",
}


class SnapshotMismatchError(ValueError):
    """Raised when a snapshotted copy does not hash-match the repository original."""


def snapshot_legacy(scripts_dir: str | Path, dest_dir: str | Path) -> list[dict[str, str]]:
    """Copy legacy sources to ``dest_dir`` and verify SHA-256 equality.

    Returns records ``[{file, sha256}]``. Raises :class:`SnapshotMismatchError`
    on any mismatch and :class:`FileNotFoundError` for missing sources.
    """
    src = Path(scripts_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for name in LEGACY_FILES:
        original = src / name
        if not original.is_file():
            raise FileNotFoundError(f"legacy source missing: {original}")
        expected = sha256_file(original)
        shutil.copy2(original, dest / name)
        actual = sha256_file(dest / name)
        if actual != expected:
            raise SnapshotMismatchError(f"snapshot hash mismatch for {name}")
        records.append({"file": name, "sha256": actual})
    return records


def verify_snapshot(scripts_dir: str | Path, dest_dir: str | Path) -> list[str]:
    """Re-check an existing snapshot; return names of files that differ/missing."""
    bad: list[str] = []
    for name in LEGACY_FILES:
        original = Path(scripts_dir) / name
        copy = Path(dest_dir) / name
        if not copy.is_file() or not original.is_file():
            bad.append(name)
        elif sha256_file(copy) != sha256_file(original):
            bad.append(name)
    return bad
