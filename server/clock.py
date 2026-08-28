"""Tid i hushållets tidszon, inte i serverns.

En VPS står nästan alltid i UTC. Utan det här visar tavlan två timmar fel på
sommaren, och en på vintern -- ett fel som ser ut som en bugg i datan snarare än
i tidszonen, och därför är otacksamt att hitta.
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from .config import Settings

WEEKDAYS = (
    "MÅNDAG", "TISDAG", "ONSDAG", "TORSDAG", "FREDAG", "LÖRDAG", "SÖNDAG",
)
MONTHS = (
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
)
# Korta veckodagsnamn som de skrivs i konfigurationen, för barnens schema.
SHORT_WEEKDAYS = ("mån", "tis", "ons", "tor", "fre", "lör", "sön")


def zone(settings: Settings) -> tzinfo:
    return ZoneInfo(settings.timezone)


def now(settings: Settings) -> datetime:
    return datetime.now(zone(settings))


def to_local(moment: datetime, settings: Settings) -> datetime:
    """Flyttar ett tidsstämplat ögonblick till hushållets tidszon."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone(settings))
    return moment.astimezone(zone(settings))


def format_date(moment: datetime) -> str:
    """'TORSDAG 28 AUGUSTI' -- som det står överst på skärmen."""
    return f"{WEEKDAYS[moment.weekday()]} {moment.day} {MONTHS[moment.month - 1].upper()}"


def weekday_key(moment: datetime) -> str:
    """'tor' -- nyckeln barnens schema är skrivet med."""
    return SHORT_WEEKDAYS[moment.weekday()]
