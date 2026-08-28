"""Avgångar från SL:s öppna api. Inga nycklar.

Tiderna visas som klockslag, inte som nedräkning. En rad som säger "avgår om två
minuter" blir direkt felaktig när skärmen inte uppdaterats på en kvart. "16:21"
åldras snyggare.
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from ..clock import zone
from ..config import Settings
from .base import Source, fetch_json, register

DEFAULT_BASE = "https://transport.integration.sl.se/v1"

MAX_DEPARTURES = 3


def parse_departures(
    payload: dict[str, Any],
    *,
    direction: str | None = None,
    walk_minutes: int = 0,
    now: datetime | None = None,
    tz: tzinfo | None = None,
    limit: int = MAX_DEPARTURES,
) -> list[dict[str, Any]]:
    """Gör om SL:s svar till en kort lista klockslag.

    Avgångar man ändå inte hinner till filtreras bort: har man fem minuters
    promenad till hållplatsen är nästa avgång om två minuter inte en avgång.
    """
    now = now or datetime.now().astimezone()
    tz = tz or now.tzinfo
    departures = []

    for item in payload.get("departures", []):
        stamp = item.get("expected") or item.get("scheduled")
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=now.tzinfo)

        if direction and direction.lower() not in (item.get("destination") or "").lower():
            continue

        minutes_away = (when - now).total_seconds() / 60
        if minutes_away < walk_minutes:
            continue

        departures.append(
            {
                "time": when.astimezone(tz).strftime("%H:%M"),
                "destination": item.get("destination") or "",
                "line": (item.get("line") or {}).get("designation") or "",
                "minutes": int(minutes_away),
            }
        )

    departures.sort(key=lambda d: d["minutes"])
    return departures[:limit]


class Transit(Source):
    key = "departures"
    ttl = 60

    def fetch(self, settings: Settings) -> list[dict[str, Any]]:
        if not settings.place.site_id:
            return []
        base = settings.endpoints.get("sl", DEFAULT_BASE).rstrip("/")
        payload = fetch_json(f"{base}/sites/{settings.place.site_id}/departures", forecast=60)
        return parse_departures(
            payload,
            direction=settings.place.direction,
            walk_minutes=settings.place.walk_minutes,
            tz=zone(settings),
        )

    def empty(self) -> list[dict[str, Any]]:
        return []


register(Transit())
