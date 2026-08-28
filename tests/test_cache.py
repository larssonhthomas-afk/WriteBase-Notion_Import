import pytest

from server.cache import TTLCache


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_fresh_values_are_reused():
    clock = Clock()
    cache = TTLCache(clock=clock)
    calls = []

    def fetch():
        calls.append(1)
        return "värde"

    assert cache.get_or_fetch("k", ttl=60, fetch=fetch) == "värde"
    clock.now += 30
    assert cache.get_or_fetch("k", ttl=60, fetch=fetch) == "värde"
    assert len(calls) == 1


def test_stale_values_are_refetched():
    clock = Clock()
    cache = TTLCache(clock=clock)
    values = iter(["första", "andra"])

    assert cache.get_or_fetch("k", 60, lambda: next(values)) == "första"
    clock.now += 61
    assert cache.get_or_fetch("k", 60, lambda: next(values)) == "andra"


def test_a_failing_source_keeps_its_last_good_value():
    """En tillfälligt onåbar tjänst ska inte tömma en yta på skärmen."""
    clock = Clock()
    cache = TTLCache(clock=clock)

    def boom():
        raise RuntimeError("nere")

    cache.get_or_fetch("k", 60, lambda: "14 grader")
    clock.now += 61
    assert cache.get_or_fetch("k", 60, boom) == "14 grader"
    assert cache.status()["k"]["stale"] is True


def test_a_source_that_never_worked_returns_nothing():
    cache = TTLCache()

    def boom():
        raise RuntimeError("nere")

    assert cache.get_or_fetch("k", 60, boom) is None


def test_status_never_leaks_values():
    cache = TTLCache()
    cache.get_or_fetch("kalender", 60, lambda: "Tandläkare 14:00")
    serialised = repr(cache.status())
    assert "Tandläkare" not in serialised
    assert set(cache.status()["kalender"]) == {"age_seconds", "stale"}
