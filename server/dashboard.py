"""Sätter ihop sammanhanget som mallen ritar.

Här och ingen annanstans bestäms vad som står på skärmen. Källorna vet inget om
layouten, mallen vet inget om nätverket.
"""
from __future__ import annotations

from typing import Any

from .cache import TTLCache
from .clock import format_date, now
from .config import Settings
from .sources import collect

DEFAULT_DEPARTURE_LABEL = "AVGÅNGAR"


def build_context(settings: Settings, cache: TTLCache) -> dict[str, Any]:
    moment = now(settings)
    context = collect(settings, cache)

    status = cache.status()
    context.update(
        {
            "clock": moment.strftime("%H:%M"),
            "date_line": format_date(moment),
            "departure_label": (settings.place.direction or DEFAULT_DEPARTURE_LABEL).upper(),
            # Markeras bara när en källa faktiskt lämnat ut gammal data, inte när
            # den bara är ohämtad.
            "stale": any(entry["stale"] for entry in status.values()),
        }
    )
    return context
