"""Väder från SMHI:s öppna data.

SMHI stängde sitt gamla prognos-api i mars 2026, vilket gör att äldre kodexempel
på nätet inte längre fungerar. Bas-url:en ligger därför i konfigurationen, så att
den går att peka om utan kodändring om den flyttar igen.
"""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any

from ..clock import zone
from ..config import Settings
from .base import Source, fetch_json, register

DEFAULT_BASE = (
    "https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point"
)

# SMHI:s vädersymboler 1-27, i klartext.
SYMBOLS: dict[int, str] = {
    1: "Klart", 2: "Mest klart", 3: "Växlande molnighet", 4: "Halvklart",
    5: "Molnigt", 6: "Mulet", 7: "Dimma", 8: "Lätt regnskur",
    9: "Regnskur", 10: "Kraftig regnskur", 11: "Åskskur",
    12: "Lätt by av regn och snö", 13: "By av regn och snö",
    14: "Kraftig by av regn och snö", 15: "Lätt snöby", 16: "Snöby",
    17: "Kraftig snöby", 18: "Lätt regn", 19: "Regn", 20: "Kraftigt regn",
    21: "Åska", 22: "Lätt snöblandat regn", 23: "Snöblandat regn",
    24: "Kraftigt snöblandat regn", 25: "Lätt snöfall", 26: "Snöfall",
    27: "Kraftigt snöfall",
}

# Vilken ikon i mallen som ritas för respektive symbol.
ICONS: dict[int, str] = {
    1: "sun", 2: "sun", 3: "partly", 4: "partly", 5: "cloud", 6: "cloud",
    7: "fog", 8: "rain", 9: "rain", 10: "rain", 11: "thunder",
    12: "sleet", 13: "sleet", 14: "sleet", 15: "snow", 16: "snow", 17: "snow",
    18: "rain", 19: "rain", 20: "rain", 21: "thunder",
    22: "sleet", 23: "sleet", 24: "sleet", 25: "snow", 26: "snow", 27: "snow",
}


def _value(entry: dict[str, Any], name: str) -> float | None:
    for parameter in entry.get("parameters", []):
        if parameter.get("name") == name:
            values = parameter.get("values") or []
            if values:
                return float(values[0])
    return None


def parse_forecast(
    payload: dict[str, Any], *, now: datetime | None = None, tz: tzinfo | None = None
) -> dict[str, Any]:
    """Plockar ut nuläget och dagens spann ur SMHI:s tidsserie."""
    now = now or datetime.now(timezone.utc)
    tz = tz or now.tzinfo or timezone.utc
    series = payload.get("timeSeries") or []
    if not series:
        raise ValueError("SMHI svarade utan timeSeries")

    parsed = []
    for entry in series:
        stamp = datetime.fromisoformat(entry["validTime"].replace("Z", "+00:00"))
        parsed.append((stamp, entry))
    parsed.sort(key=lambda item: item[0])

    current = next((e for t, e in parsed if t >= now), parsed[0][1])
    symbol = int(_value(current, "Wsymb2") or 0)

    today = now.astimezone(tz).date()
    todays = [e for t, e in parsed if t.astimezone(tz).date() == today]
    temperatures = [v for v in (_value(e, "t") for e in todays or [current]) if v is not None]

    # Första timmen idag med nederbörd värd att nämna.
    rain_at = None
    for stamp, entry in parsed:
        if stamp.astimezone(tz).date() != today or stamp < now:
            continue
        if (_value(entry, "pmean") or 0) >= 0.2:
            rain_at = stamp.astimezone(tz).strftime("%H:%M")
            break

    return {
        "temperature": round(_value(current, "t") or 0),
        "description": SYMBOLS.get(symbol, ""),
        "icon": ICONS.get(symbol, "cloud"),
        "low": round(min(temperatures)) if temperatures else None,
        "high": round(max(temperatures)) if temperatures else None,
        "rain_at": rain_at,
    }


class Weather(Source):
    key = "weather"
    ttl = 30 * 60

    def fetch(self, settings: Settings) -> dict[str, Any]:
        base = settings.endpoints.get("smhi", DEFAULT_BASE).rstrip("/")
        url = f"{base}/lon/{settings.place.longitude:.4f}/lat/{settings.place.latitude:.4f}/data.json"
        return parse_forecast(fetch_json(url), tz=zone(settings))


register(Weather())
