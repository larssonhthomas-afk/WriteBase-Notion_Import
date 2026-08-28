"""Inställningar.

Hemligheter kommer från miljövariabler. Allt som beskriver hushållet -- vilken
hållplats, vilken skola, vilka barn -- ligger i en YAML-fil, så att det går att
ändra utan att röra koden.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .framebuffer import PANEL_HEIGHT, PANEL_WIDTH  # noqa: F401  (vidarebefordras)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config.yaml"

# Minsta godtagbara längd på delad hemlighet. En kort token är ingen token.
MIN_TOKEN_LENGTH = 32


class ConfigError(RuntimeError):
    """Uppstartsfel som beror på saknad eller orimlig konfiguration."""


@dataclass(frozen=True)
class Place:
    """Var hushållet finns, för väder och avgångar."""

    latitude: float = 59.3293
    longitude: float = 18.0686
    site_id: int | None = None
    direction: str | None = None
    walk_minutes: int = 0


@dataclass(frozen=True)
class Child:
    name: str
    school_start: str | None = None
    sport_days: tuple[str, ...] = ()


@dataclass(frozen=True)
class Settings:
    place: Place = field(default_factory=Place)
    children: tuple[Child, ...] = ()
    school_slug: str | None = None
    calendar_urls: tuple[str, ...] = ()
    calendar_provider: str | None = None
    timezone: str = "Europe/Stockholm"
    endpoints: dict[str, str] = field(default_factory=dict)
    token: str = ""

    @property
    def has_token(self) -> bool:
        return len(self.token) >= MIN_TOKEN_LENGTH


def _as_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def load_settings(path: Path | None = None, *, require_token: bool = False) -> Settings:
    """Läser config.yaml plus miljövariabler.

    Saknas filen används rimliga standardvärden, så att renderaren går att köra
    direkt efter en klon utan att något behöver fyllas i först.
    """
    path = path or Path(os.environ.get("DASHBOARD_CONFIG", DEFAULT_CONFIG))
    raw: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded:
            raw = loaded

    place_raw = raw.get("place") or {}
    place = Place(
        latitude=float(place_raw.get("latitude", 59.3293)),
        longitude=float(place_raw.get("longitude", 18.0686)),
        site_id=place_raw.get("site_id"),
        direction=place_raw.get("direction"),
        walk_minutes=int(place_raw.get("walk_minutes", 0)),
    )

    children = tuple(
        Child(
            name=str(c["name"]),
            school_start=c.get("school_start"),
            sport_days=_as_tuple(c.get("sport_days")),
        )
        for c in (raw.get("children") or [])
    )

    token = os.environ.get("DASHBOARD_TOKEN", "")
    if require_token and len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            "DASHBOARD_TOKEN saknas eller är för kort. Bilden innehåller "
            f"kalenderdata i klartext och får inte lämnas ut oskyddad. "
            f"Sätt minst {MIN_TOKEN_LENGTH} tecken: "
            "export DASHBOARD_TOKEN=$(openssl rand -hex 32)"
        )

    return Settings(
        place=place,
        children=children,
        school_slug=raw.get("school_slug"),
        calendar_urls=_as_tuple(raw.get("calendar_urls")),
        calendar_provider=raw.get("calendar_provider"),
        timezone=raw.get("timezone", "Europe/Stockholm"),
        endpoints=dict(raw.get("endpoints") or {}),
        token=token,
    )
