"""Webbtjänsten som lämnar ut bilden.

Servern står på internet och bilden innehåller familjens dag i klartext -- namn,
tider, var barnen är. Därför krävs en delad hemlighet för varje hämtning, och
tjänsten vägrar starta utan en.

Renderingen sker inte per anrop utan högst en gång per RENDER_TTL sekunder.
Skärmen frågar varje minut och är den enda klienten, men det skyddar ändå mot att
en omladdad flik eller en omstartad Pi utlöser en skur av renderingar.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from time import monotonic
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response

from .cache import TTLCache
from .config import Settings, load_settings
from .dashboard import build_context
from .framebuffer import to_panel_buffer
from .render import Renderer

log = logging.getLogger(__name__)

# Hur länge en renderad bild återanvänds. Klockan visar hela minuter, så kortare
# än så vore bortkastat arbete.
RENDER_TTL = 50.0

PNG_MEDIA_TYPE = "image/png"
BIN_MEDIA_TYPE = "application/octet-stream"


@dataclass
class Frame:
    png: bytes
    raw: bytes
    etag: str
    rendered_at: float


def etag_for(payload: bytes) -> str:
    return '"' + hashlib.sha256(payload).hexdigest()[:32] + '"'


def matches(header: str | None, etag: str) -> bool:
    """Sant om klienten redan har just den här bilden.

    If-None-Match kan innehålla flera värden och en svag-markör.
    """
    if not header:
        return False
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag or candidate == "*":
            return True
    return False


class Dashboard:
    """Håller aktuell bildruta och renderar om den när den blivit gammal."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache = TTLCache()
        self.renderer = Renderer()
        self._frame: Frame | None = None

    async def frame(self) -> Frame:
        if self._frame is not None and monotonic() - self._frame.rendered_at < RENDER_TTL:
            return self._frame

        context = build_context(self.settings, self.cache)
        image = await self.renderer.render(context)

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        png = buffer.getvalue()

        self._frame = Frame(
            png=png, raw=to_panel_buffer(image), etag=etag_for(png), rendered_at=monotonic()
        )
        return self._frame

    def require_token(self, authorization: str | None) -> None:
        """Jämför hemligheten i konstant tid, så att svarstiden inte läcker den."""
        expected = f"Bearer {self.settings.token}"
        if not authorization or not secrets.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=401,
                detail="ogiltig eller saknad token",
                headers={"WWW-Authenticate": "Bearer"},
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings(require_token=True)
    dashboard = Dashboard(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await dashboard.renderer.stop()

    app = FastAPI(title="hallskärmen", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.dashboard = dashboard

    async def deliver(
        request: Request, authorization: str | None, *, raw: bool
    ) -> Response:
        dashboard.require_token(authorization)
        frame = await dashboard.frame()

        if matches(request.headers.get("if-none-match"), frame.etag):
            return Response(status_code=304, headers={"ETag": frame.etag})

        payload = frame.raw if raw else frame.png
        return Response(
            content=payload,
            media_type=BIN_MEDIA_TYPE if raw else PNG_MEDIA_TYPE,
            headers={"ETag": frame.etag, "Cache-Control": "no-cache"},
        )

    @app.get("/dashboard.png")
    async def dashboard_png(request: Request, authorization: str | None = Header(default=None)):
        return await deliver(request, authorization, raw=False)

    @app.get("/dashboard.bin")
    async def dashboard_bin(request: Request, authorization: str | None = Header(default=None)):
        """Samma bild, färdigpackad för panelen.

        Används inte av Pi-klienten, som avkodar PNG utan besvär. Finns för en
        framtida mikrokontroller, som varken har PIL eller minne att avkoda med.
        """
        return await deliver(request, authorization, raw=True)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Öppen, och innehåller därför bara åldrar -- aldrig något innehåll."""
        return {"ok": True, "sources": dashboard.cache.status()}

    return app
