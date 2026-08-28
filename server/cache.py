"""Cache med hållbarhetstid, som behåller gammal data när en källa fallerar.

Skärmen ritas om varje minut, men källorna ändrar sig långsammare än så. Utan
cache skulle SMHI och skolmaten.se få 1 440 anrop om dygnet var.

Att gammalt värde lämnas ut när hämtningen misslyckas är avsiktligt: en
tillfälligt onåbar väderleverantör ska inte tömma en yta på skärmen.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Entry:
    value: Any
    fetched_at: float
    stale: bool = False

    def age(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) - self.fetched_at


class TTLCache:
    """Trådsäker nyckel/värde-cache där varje nyckel har egen hållbarhetstid."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._entries: dict[str, Entry] = {}
        self._lock = Lock()

    def get_or_fetch(self, key: str, ttl: float, fetch: Callable[[], T]) -> T | None:
        """Returnerar cachat värde om det är färskt, annars hämtar det på nytt.

        Misslyckas hämtningen returneras det gamla värdet märkt som inaktuellt.
        Finns inget gammalt värde returneras None -- anroparen får då rendera
        ytan tom hellre än att hela bilden uteblir.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.age(self._clock()) < ttl:
                return entry.value

        try:
            value = fetch()
        except Exception:
            log.warning("källan %r gick inte att hämta", key, exc_info=True)
            with self._lock:
                entry = self._entries.get(key)
                if entry is None:
                    return None
                entry.stale = True
                return entry.value

        with self._lock:
            self._entries[key] = Entry(value=value, fetched_at=self._clock())
        return value

    def status(self) -> dict[str, dict[str, Any]]:
        """Ålder och färskhet per nyckel. Innehåller aldrig något värde."""
        now = self._clock()
        with self._lock:
            return {
                key: {"age_seconds": round(entry.age(now), 1), "stale": entry.stale}
                for key, entry in self._entries.items()
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
