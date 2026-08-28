"""Gemensam grund för datakällorna.

En källa hämtar en sak, kan bara sin egen tjänst, och vet ingenting om hur den
visas. Den returnerar vanliga dictar -- mallen bestämmer utseendet.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Iterable

import httpx

from ..cache import TTLCache
from ..config import Settings

log = logging.getLogger(__name__)

# Kort timeout med flit. Skärmen ska hellre visa en gammal siffra än hänga sig
# på en tjänst som inte svarar.
HTTP_TIMEOUT = 8.0
USER_AGENT = "hallskarmen/1.0 (+https://github.com/larssonhthomas-afk)"


def fetch_text(url: str, **params: Any) -> str:
    with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(url, params=params or None, follow_redirects=True)
        response.raise_for_status()
        return response.text


def fetch_json(url: str, **params: Any) -> Any:
    with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(url, params=params or None, follow_redirects=True)
        response.raise_for_status()
        return response.json()


class Source(ABC):
    """En datakälla.

    ``key`` namnger både cacheposten och variabeln som mallen ser.
    ``ttl`` är hur länge ett hämtat värde duger, i sekunder.
    """

    key: str
    ttl: float

    @abstractmethod
    def fetch(self, settings: Settings) -> Any:
        """Hämtar färsk data. Får kasta -- cachen fångar och behåller det gamla."""

    def empty(self) -> Any:
        """Vad mallen ser när källan aldrig lyckats hämta något."""
        return None


registry: list[Source] = []


def register(source: Source) -> Source:
    registry.append(source)
    return source


def collect(
    settings: Settings, cache: TTLCache, sources: Iterable[Source] | None = None
) -> dict[str, Any]:
    """Kör alla källor och samlar resultatet till ett sammanhang för mallen.

    En källa som fallerar tar aldrig med sig de andra -- ytan blir tom, resten
    av skärmen ritas som vanligt.
    """
    context: dict[str, Any] = {}
    for source in sources if sources is not None else registry:
        value = cache.get_or_fetch(source.key, source.ttl, lambda s=source: s.fetch(settings))
        context[source.key] = source.empty() if value is None else value
    return context
