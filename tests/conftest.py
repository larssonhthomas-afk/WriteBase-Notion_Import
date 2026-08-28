import io
import os
from pathlib import Path

import pytest
from PIL import Image

from server.config import Child, Place, Settings
from server.framebuffer import PANEL_HEIGHT, PANEL_WIDTH

# Chromium ligger på olika ställen beroende på hur Playwright installerats.
CHROMIUM_CANDIDATES = [
    os.environ.get("CHROMIUM_PATH", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]


@pytest.fixture(scope="session", autouse=True)
def chromium() -> None:
    if os.environ.get("CHROMIUM_PATH"):
        return
    for candidate in CHROMIUM_CANDIDATES:
        if candidate and Path(candidate).exists():
            os.environ["CHROMIUM_PATH"] = candidate
            return


@pytest.fixture
def settings() -> Settings:
    return Settings(
        place=Place(latitude=59.3293, longitude=18.0686, site_id=9001, direction="Kungsträdgården", walk_minutes=5),
        children=(Child(name="Ella", school_start="07:55", sport_days=("tis", "tor")),),
        school_slug="testskolan",
        timezone="Europe/Stockholm",
        token="t" * 40,
    )


@pytest.fixture
def blank() -> Image.Image:
    return Image.new("1", (PANEL_WIDTH, PANEL_HEIGHT), 1)


def as_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
