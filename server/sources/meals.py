"""Skolmat från skolmaten.se via RSS. Ingen inloggning, ingen nyckel."""
from __future__ import annotations

import re
from datetime import date
from typing import Any
from xml.etree import ElementTree

from ..config import Settings
from .base import Source, fetch_text, register

DEFAULT_BASE = "https://skolmaten.se"

# Rubrikerna ser ut som "Torsdag 28 augusti". Vi vill åt dagen i månaden.
DAY_IN_TITLE = re.compile(r"\b(\d{1,2})\b")

MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10,
    "november": 11, "december": 12,
}

VEGETARIAN = re.compile(r"^\s*(vegetarisk[t]?|veg|vegan)\s*[:\-]\s*", re.IGNORECASE)


def parse_menu(xml: str, *, today: date) -> dict[str, Any]:
    """Plockar ut dagens rätter ur veckoflödet.

    Flödet innehåller hela veckan. Vi matchar på dag och månad i rubriken, inte
    på ordningen i listan, eftersom listan börjar på veckans första dag.
    """
    root = ElementTree.fromstring(xml)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        lowered = title.lower()

        day_match = DAY_IN_TITLE.search(lowered)
        month = next((n for name, n in MONTHS.items() if name in lowered), None)
        if not day_match or month is None:
            continue
        if int(day_match.group(1)) != today.day or month != today.month:
            continue

        description = item.findtext("description") or ""
        parts = [
            re.sub(r"<[^>]+>", "", line).strip()
            for line in re.split(r"<br\s*/?>|\n", description)
        ]
        dishes = [p for p in parts if p]
        if not dishes:
            continue

        main, alternatives = dishes[0], dishes[1:]
        vegetarian = next((VEGETARIAN.sub("", d) for d in alternatives if VEGETARIAN.match(d)), None)
        return {"main": main, "alternatives": alternatives, "vegetarian": vegetarian}

    return {"main": None, "alternatives": [], "vegetarian": None}


class Meals(Source):
    key = "meal"
    ttl = 6 * 60 * 60

    def fetch(self, settings: Settings) -> dict[str, Any]:
        if not settings.school_slug:
            return self.empty()
        base = settings.endpoints.get("skolmaten", DEFAULT_BASE).rstrip("/")
        xml = fetch_text(f"{base}/{settings.school_slug}/rss/weeks/")
        return parse_menu(xml, today=date.today())

    def empty(self) -> dict[str, Any]:
        return {"main": None, "alternatives": [], "vegetarian": None}


register(Meals())
