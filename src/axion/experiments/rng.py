"""Deterministic, independently owned random-number streams.

Phase 0 finding R-03: legacy scripts share global ``random`` / ``np.random``
state (sensor noise, SA draws, and observation sampling all draw from the same
stream), and each script fixes a single global seed. New infrastructure must
not repeat that pattern, and must not silently rewire legacy globals (which
would change historical outputs).

This module derives one independent generator per subsystem from a single
root seed, using ``numpy.random.SeedSequence.spawn`` (guaranteed independent
streams) for NumPy and domain-separated ``random.Random`` instances for the
standard library. Legacy scripts do not use this module.
"""

from __future__ import annotations

import random

import numpy as np

STREAMS: tuple[str, ...] = ("workload", "init", "sensor", "optimization")


def make_numpy_streams(root_seed: int) -> dict[str, np.random.Generator]:
    """Derive one independent ``Generator`` per subsystem stream.

    Same ``root_seed`` always reproduces the same streams; advancing one
    stream never affects another.
    """
    if isinstance(root_seed, bool) or not isinstance(root_seed, int):
        raise TypeError("root_seed must be an integer")
    if not 0 <= root_seed < 2**32:
        raise ValueError("root_seed must be in [0, 2**32)")
    children = np.random.SeedSequence(int(root_seed)).spawn(len(STREAMS))
    return {name: np.random.default_rng(child) for name, child in zip(STREAMS, children)}


def make_stdlib_streams(root_seed: int) -> dict[str, random.Random]:
    """Derive one independent ``random.Random`` per subsystem stream."""
    if isinstance(root_seed, bool) or not isinstance(root_seed, int):
        raise TypeError("root_seed must be an integer")
    if not 0 <= root_seed < 2**32:
        raise ValueError("root_seed must be in [0, 2**32)")
    return {name: random.Random(f"axion-v1:{root_seed}:{name}") for name in STREAMS}


def stream_seeds(root_seed: int) -> dict[str, int]:
    """Public seed schedule: the integer seed material behind each stream.

    Useful for manifest ``subsystem_seeds`` when a consumer cannot serialize
    generator state. NumPy child keys are 128-bit; they are folded to 32 bits
    for recording (the streams themselves remain full-entropy).
    """
    children = np.random.SeedSequence(int(root_seed)).spawn(len(STREAMS))
    out: dict[str, int] = {}
    for name, child in zip(STREAMS, children):
        entropy = int(child.entropy) if child.entropy is not None else root_seed
        out[name] = entropy % 2**32
    return out
