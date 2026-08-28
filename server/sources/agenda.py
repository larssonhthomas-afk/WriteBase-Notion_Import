"""Dagens händelser: familjekalendern plus barnens fasta tider.

Kalendern kan komma två vägar. Antingen som publicerade ICS-länkar, eller från
kod du redan har på servern -- peka ut den med ``calendar_provider`` i
config.yaml, på formen ``mitt_paket.kalender:hamta_dagen``. Funktionen anropas
med (settings, day) och ska returnera en lista med händelser.

Publicerade ICS-länkar är öppna för den som har adressen. Sprids länken kan vem
som helst läsa kalendern.
"""
from __future__ import annotations

import importlib
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

import recurring_ical_events
from icalendar import Calendar

from ..clock import to_local, weekday_key, zone
from ..config import Settings
from .base import Source, fetch_text, register

log = logging.getLogger(__name__)

SPORT_ICON = "run"


def load_provider(path: str) -> Callable[..., Any]:
    """Laddar ``modul:funktion`` som användaren pekat ut i konfigurationen."""
    module_name, _, attribute = path.partition(":")
    if not module_name or not attribute:
        raise ValueError(f"calendar_provider ska skrivas som 'modul:funktion', fick {path!r}")
    return getattr(importlib.import_module(module_name), attribute)


def parse_ics(text: str, *, day: date, settings: Settings) -> list[dict[str, Any]]:
    """Plockar ut dagens händelser ur en ICS-fil.

    Återkommande händelser expanderas -- träningen varje tisdag ligger som en
    enda post med en upprepningsregel, inte som femtio poster.
    """
    calendar = Calendar.from_ical(text)
    start = datetime.combine(day, time.min, tzinfo=zone(settings))
    events = recurring_ical_events.of(calendar).between(start, start + timedelta(days=1))

    parsed: list[dict[str, Any]] = []
    for event in events:
        begins = event.get("DTSTART")
        title = str(event.get("SUMMARY") or "").strip()
        if not title:
            continue

        value = begins.dt if begins is not None else None
        if isinstance(value, datetime):
            local = to_local(value, settings)
            parsed.append(
                {"time": local.strftime("%H:%M"), "title": title, "sort": local.hour * 60 + local.minute}
            )
        else:
            # Heldagshändelse: ingen klockslag, ska ligga överst.
            parsed.append({"time": None, "title": title, "sort": -1})
    return parsed


def schedule_entries(settings: Settings, day: date) -> list[dict[str, Any]]:
    """Barnens skolstart och idrottsdagar.

    Infomentor saknar öppet gränssnitt, och flera kommuner har gått över till
    inloggning med bank-id. Tiderna matas därför in för hand i config.yaml.
    """
    key = weekday_key(datetime.combine(day, time.min))
    entries: list[dict[str, Any]] = []
    for child in settings.children:
        if not child.school_start:
            continue
        hour, _, minute = child.school_start.partition(":")
        has_sport = key in child.sport_days
        entries.append(
            {
                "time": child.school_start,
                "title": f"{child.name} — skolstart",
                "icon": SPORT_ICON if has_sport else None,
                "sort": int(hour) * 60 + int(minute or 0),
            }
        )
    return entries


class Agenda(Source):
    key = "agenda"
    ttl = 15 * 60

    def fetch(self, settings: Settings) -> list[dict[str, Any]]:
        day = date.today()
        events: list[dict[str, Any]] = []

        for url in settings.calendar_urls:
            try:
                events.extend(parse_ics(fetch_text(url), day=day, settings=settings))
            except Exception:
                # En trasig kalender ska inte tömma de andra.
                log.warning("kalendern %s gick inte att läsa", url, exc_info=True)

        if settings.calendar_provider:
            provider = load_provider(settings.calendar_provider)
            for event in provider(settings, day) or []:
                events.append(normalise(event, settings))

        events.extend(schedule_entries(settings, day))
        events.sort(key=lambda e: e["sort"])
        return events

    def empty(self) -> list[dict[str, Any]]:
        return []


def normalise(event: Any, settings: Settings) -> dict[str, Any]:
    """Tar emot vad din egen kod än returnerar och gör det till en rad på skärmen.

    Accepterar dict med ``title`` och valfri ``start`` (datetime) eller ``time``
    (sträng), eller ett objekt med samma attribut.
    """
    get = event.get if isinstance(event, dict) else lambda k, d=None: getattr(event, k, d)
    title = str(get("title") or get("summary") or "").strip()
    start = get("start") or get("dtstart")

    if isinstance(start, datetime):
        local = to_local(start, settings)
        return {
            "time": local.strftime("%H:%M"),
            "title": title,
            "icon": get("icon"),
            "sort": local.hour * 60 + local.minute,
        }

    stamp = get("time")
    if stamp:
        hour, _, minute = str(stamp).partition(":")
        return {
            "time": str(stamp),
            "title": title,
            "icon": get("icon"),
            "sort": int(hour) * 60 + int(minute or 0),
        }
    return {"time": None, "title": title, "icon": get("icon"), "sort": -1}


register(Agenda())
