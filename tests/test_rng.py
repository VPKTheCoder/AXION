"""Independent RNG streams: reproducibility + isolation (P1.2, R-03)."""

import numpy as np
import pytest

from axion.experiments import rng as RNG


def test_stream_names():
    assert set(RNG.STREAMS) == {"workload", "init", "sensor", "optimization"}


def test_numpy_reproducible():
    a = RNG.make_numpy_streams(7)
    b = RNG.make_numpy_streams(7)
    for name in RNG.STREAMS:
        assert np.array_equal(a[name].integers(0, 2**31, 100),
                              b[name].integers(0, 2**31, 100))


def test_numpy_streams_independent():
    streams = RNG.make_numpy_streams(11)
    # Consume heavily from one stream; the others must be unaffected,
    # i.e. identical to a freshly constructed set advanced the same way.
    streams["workload"].random(10_000)
    fresh = RNG.make_numpy_streams(11)
    assert np.array_equal(streams["sensor"].random(1000),
                          fresh["sensor"].random(1000))
    assert np.array_equal(streams["init"].random(1000),
                          fresh["init"].random(1000))
    # Distinct streams differ with overwhelming probability over 1000 draws.
    draws = {n: RNG.make_numpy_streams(11)[n].random(1000) for n in RNG.STREAMS}
    assert not np.array_equal(draws["workload"], draws["sensor"])


def test_stdlib_reproducible_and_independent():
    a = RNG.make_stdlib_streams(3)
    b = RNG.make_stdlib_streams(3)
    assert [a["init"].random() for _ in range(5)] == [b["init"].random() for _ in range(5)]
    assert a["init"].random() != a["sensor"].random()


def test_bad_seeds_rejected():
    for bad in (-1, 2**32, True, "0", None, 1.5):
        with pytest.raises((TypeError, ValueError)):
            RNG.make_numpy_streams(bad)
        with pytest.raises((TypeError, ValueError)):
            RNG.make_stdlib_streams(bad)


def test_stream_seeds_stable():
    assert RNG.stream_seeds(42) == RNG.stream_seeds(42)
    assert set(RNG.stream_seeds(42)) == set(RNG.STREAMS)
