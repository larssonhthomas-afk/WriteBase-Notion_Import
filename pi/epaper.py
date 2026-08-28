"""Tunn insvepning runt Waveshares drivrutin.

Två skäl att inte anropa drivrutinen direkt. Dels heter metoderna olika i olika
versioner av Waveshares bibliotek, och ett tydligt fel vid uppstart är bättre än
ett AttributeError mitt i natten. Dels går klienten att köra och testa på en
maskin utan panel, vilket är hela skillnaden mellan att kunna felsöka och inte.

Panelen sövs efter varje uppdatering. Att lämna den under spänning kan skada den
-- det är den enda vägen att göra sönder hårdvaran med mjukvara, så det görs i
en finally-sats och inte som ett hoppfullt sista anrop.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from PIL import Image

log = logging.getLogger(__name__)

# Metodnamnen har skiftat mellan versioner av waveshare_epd.
INIT_FULL = ("init",)
INIT_PARTIAL = ("init_part", "init_Part", "init_fast")
DISPLAY_FULL = ("display",)
DISPLAY_PARTIAL = ("display_Partial", "display_Part", "displayPartial")


class Panel(Protocol):
    def show(self, image: Image.Image) -> None: ...
    def show_region(self, image: Image.Image, region: tuple[int, int, int, int]) -> None: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


def _resolve(driver: Any, names: tuple[str, ...]) -> Callable[..., Any]:
    for name in names:
        method = getattr(driver, name, None)
        if callable(method):
            return method
    available = ", ".join(sorted(n for n in dir(driver) if not n.startswith("_")))
    raise AttributeError(
        f"hittade ingen av {names} i drivrutinen. Tillgängliga metoder: {available}"
    )


class WavesharedPanel:
    """Riktig panel via waveshare_epd.epd7in5_V2."""

    def __init__(self) -> None:
        from waveshare_epd import epd7in5_V2  # importeras sent: finns bara på Pi:n

        self._epd = epd7in5_V2.EPD()
        self._partial_ready = False

    def _buffer(self, image: Image.Image):
        return self._epd.getbuffer(image)

    def show(self, image: Image.Image) -> None:
        """Full omritning. Blinkar, och suddar samtidigt bort spökrester."""
        try:
            _resolve(self._epd, INIT_FULL)()
            _resolve(self._epd, DISPLAY_FULL)(self._buffer(image))
        finally:
            self._epd.sleep()
        self._partial_ready = False

    def show_region(self, image: Image.Image, region: tuple[int, int, int, int]) -> None:
        """Partiell uppdatering av en delruta. Byter innehåll utan att blinka."""
        x, y, width, height = region
        try:
            _resolve(self._epd, INIT_PARTIAL)()
            _resolve(self._epd, DISPLAY_PARTIAL)(
                self._buffer(image), x, y, x + width, y + height
            )
        finally:
            self._epd.sleep()
        self._partial_ready = True

    def clear(self) -> None:
        try:
            _resolve(self._epd, INIT_FULL)()
            self._epd.Clear()
        finally:
            self._epd.sleep()

    def close(self) -> None:
        try:
            from waveshare_epd import epdconfig

            epdconfig.module_exit(cleanup=True)
        except Exception:
            log.debug("kunde inte stänga ned drivrutinen", exc_info=True)


class NullPanel:
    """Loggar i stället för att rita. Låter klienten köras utan hårdvara."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def show(self, image: Image.Image) -> None:
        self.calls.append(("show", image.size))
        log.info("full omritning %sx%s", *image.size)

    def show_region(self, image: Image.Image, region: tuple[int, int, int, int]) -> None:
        self.calls.append(("show_region", region))
        log.info("partiell uppdatering %s", region)

    def clear(self) -> None:
        self.calls.append(("clear", None))

    def close(self) -> None:
        self.calls.append(("close", None))


def open_panel(*, dry_run: bool = False) -> Panel:
    """Riktig panel om drivrutinen finns, annars en som bara loggar."""
    if dry_run:
        return NullPanel()
    try:
        return WavesharedPanel()
    except ImportError:
        log.warning("waveshare_epd saknas -- kör utan panel")
        return NullPanel()
