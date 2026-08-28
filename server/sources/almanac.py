"""Namnsdag och en historisk händelse. Utfyllnad, inte information.

Båda ytorna får vara tomma. De behövs inte för att skärmen ska göra sitt jobb,
och ska aldrig kunna sänka resten av bilden.

Namnsdagarna hämtas inte över nätet. Det finns inget öppet api värt namnet, och
en tabell på 365 rader som är fel på några ställen är sämre än ingen tabell alls.
Lägg in data/namnsdagar.json med formen {"08-28": "Gunnar, Gunder"} om du vill ha
ytan ifylld.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from ..config import REPO_ROOT, Settings
from .base import Source, fetch_json, register

NAME_DAYS_FILE = REPO_ROOT / "data" / "namnsdagar.json"
DEFAULT_ONTHISDAY = "https://api.wikimedia.org/feed/v1/wikipedia/sv/onthisday/events"

# Wikipedia listar dagens händelser nyast först. De äldre är oftast trevligare
# att läsa i en hall, och slipper dagsaktuell politik.
PREFER_OLDER_THAN = 1990


def name_day(day: date) -> str | None:
    if not NAME_DAYS_FILE.exists():
        return None
    table = json.loads(NAME_DAYS_FILE.read_text(encoding="utf-8"))
    return table.get(day.strftime("%m-%d")) or None


def pick_event(payload: dict[str, Any]) -> str | None:
    events = payload.get("events") or []
    if not events:
        return None
    older = [e for e in events if isinstance(e.get("year"), int) and e["year"] < PREFER_OLDER_THAN]
    chosen = (older or events)[0]
    text = str(chosen.get("text") or "").strip()
    year = chosen.get("year")
    if not text:
        return None
    return f"{year} — {text}" if year else text


class Almanac(Source):
    key = "almanac"
    ttl = 24 * 60 * 60

    def fetch(self, settings: Settings) -> dict[str, Any]:
        today = date.today()
        base = settings.endpoints.get("onthisday", DEFAULT_ONTHISDAY).rstrip("/")
        try:
            event = pick_event(fetch_json(f"{base}/{today.month}/{today.day}"))
        except Exception:
            event = None
        return {"name_day": name_day(today), "event": event}

    def empty(self) -> dict[str, Any]:
        return {"name_day": None, "event": None}


register(Almanac())
