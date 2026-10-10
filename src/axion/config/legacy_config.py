"""Read-only access to the legacy configuration (``Scripts/core.py``).

Only ``core.py`` is ever imported, and only via :func:`load_core`, because it
is side-effect free (it defines constants and classes; it writes nothing and
seeds nothing at import time). The legacy *simulation* modules
(``tats_simulation``, ``axion``, ``ecm_simulation``) reseed global RNG state on
import and must only ever run in isolated subprocesses (see
:mod:`axion.experiments.runner` and :mod:`axion.constraints.legacy_adapter`).
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def load_core(scripts_dir: str | Path) -> ModuleType:
    """Import ``Scripts/core.py`` by path without touching ``sys.path`` globals."""
    core_path = Path(scripts_dir) / "core.py"
    if not core_path.is_file():
        raise FileNotFoundError(f"legacy core.py not found at {core_path}")
    spec = importlib.util.spec_from_file_location("_axion_legacy_core", core_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load legacy core from {core_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):  # numpy arrays / scalars
        return _jsonable(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def serialize_cfg(core: ModuleType) -> dict[str, Any]:
    """Serialize the legacy ``CFG`` mapping (plus derived vectors) to plain JSON types."""
    cfg = dict(core.CFG)
    data = _jsonable(cfg)
    data["_derived"] = {
        "N": int(core.N),
        "W_DIM": int(core.W_DIM),
        "WORKLOAD_POWER": _jsonable(core.W_POW),
        "WORKLOAD_LAT": _jsonable(core.W_LAT),
        "ALLOWED_CAPS": [[float(c) for c in caps] for caps in core.ALLOWED_CAPS],
    }
    return data


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
