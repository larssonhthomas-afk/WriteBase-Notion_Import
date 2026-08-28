"""HTML in, svartvit bild ut.

Layouten är CSS, inte koordinater. Det är hela poängen med att rendera på
servern: en ändring går att förhandsgranska i en webbläsarflik i stället för att
skickas till hallen och tittas på från en meter håll.

Webbläsaren hålls varm mellan renderingarna. Att starta Chromium tar ungefär en
sekund; att fotografera en sida i en redan igång webbläsare tar tiotals
millisekunder.
"""
from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.async_api import Browser, async_playwright

from ..config import PANEL_HEIGHT, PANEL_WIDTH
from ..framebuffer import to_monochrome

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "template.html"

# Webbtypsnitt får ta så här lång tid, sedan ritas sidan ändå. En långsam
# typsnittsserver ska aldrig kunna stoppa skärmen -- reservtypsnittet duger.
FONT_TIMEOUT_MS = 2500

_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(context: dict[str, Any]) -> str:
    """Fyller mallen. Skild från skärmdumpen så att den går att testa ensam."""
    return _environment.get_template(TEMPLATE_NAME).render(**context)


def chromium_path() -> str | None:
    """Var Chromium ligger, om den inte ligger där Playwright förväntar sig."""
    return os.environ.get("CHROMIUM_PATH") or None


class Renderer:
    """Håller en varm webbläsare och gör om sammanhang till färdiga bilder."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            executable_path=chromium_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--force-color-profile=srgb"],
        )
        log.info("chromium startad")

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def render(self, context: dict[str, Any]) -> Image.Image:
        """Renderar sammanhanget till en svartvit 800x480-bild."""
        html = render_html(context)
        async with self._lock:
            await self.start()
            assert self._browser is not None
            page = await self._browser.new_page(
                viewport={"width": PANEL_WIDTH, "height": PANEL_HEIGHT},
                device_scale_factor=1,
            )
            try:
                await page.set_content(html, wait_until="load")
                try:
                    await page.evaluate("document.fonts.ready", timeout=FONT_TIMEOUT_MS)
                except Exception:
                    log.debug("typsnitt hann inte laddas, ritar med reservtypsnitt")
                shot = await page.screenshot(type="png")
            finally:
                await page.close()

        return to_monochrome(Image.open(BytesIO(shot)))

    def render_sync(self, context: dict[str, Any]) -> Image.Image:
        """Bekvämlighet för skript och tester som inte redan kör asynkront."""
        return asyncio.run(self._render_once(context))

    async def _render_once(self, context: dict[str, Any]) -> Image.Image:
        try:
            return await self.render(context)
        finally:
            await self.stop()
