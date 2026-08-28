"""Omvandling mellan bild och det panelen faktiskt vill ha.

Waveshares 7,5-tumspanel tar en bit per pixel, åtta pixlar per byte, högsta
biten först. En etta är vit och en nolla är svart -- alltså tvärtom mot vad man
gissar. Hela skärmen blir 800 * 480 / 8 = 48 000 byte.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

PANEL_WIDTH = 800
PANEL_HEIGHT = 480

BUFFER_SIZE = PANEL_WIDTH * PANEL_HEIGHT // 8

# Partiella uppdateringar packas åtta pixlar per byte, så en delruta måste börja
# och sluta på en jämn bytegräns i sidled.
X_ALIGNMENT = 8

# Ändras mer än så här av skärmen ritas allt om. En partiell uppdatering av nästan
# hela ytan är långsammare än en hel omritning, och lämnar dessutom spökrester.
FULL_REDRAW_FRACTION = 0.45


def to_monochrome(image: Image.Image, threshold: int = 128) -> Image.Image:
    """Gör om en bild till rent svartvitt utan gråtoner.

    Tröskling, inte gitterrastrering. Text ska vara skarp; ett raster gör
    bokstäver gryniga på e-ink.
    """
    grey = image.convert("L")
    return grey.point(lambda p: 255 if p > threshold else 0, mode="1")


def to_panel_buffer(image: Image.Image) -> bytes:
    """Packar en svartvit bild till panelens bitformat."""
    if image.size != (PANEL_WIDTH, PANEL_HEIGHT):
        raise ValueError(
            f"panelen är {PANEL_WIDTH}x{PANEL_HEIGHT}, fick {image.size[0]}x{image.size[1]}"
        )
    pixels = np.array(image.convert("1"), dtype=np.uint8)
    packed = np.packbits(pixels, axis=1, bitorder="big")
    return packed.tobytes()


def from_panel_buffer(buffer: bytes) -> Image.Image:
    """Motsatsen till to_panel_buffer. Används av testerna."""
    if len(buffer) != BUFFER_SIZE:
        raise ValueError(f"förväntade {BUFFER_SIZE} byte, fick {len(buffer)}")
    packed = np.frombuffer(buffer, dtype=np.uint8).reshape(PANEL_HEIGHT, PANEL_WIDTH // 8)
    pixels = np.unpackbits(packed, axis=1, bitorder="big")
    return Image.fromarray((pixels * 255).astype(np.uint8), mode="L").convert("1")


def dirty_region(
    previous: Image.Image | None, current: Image.Image
) -> tuple[int, int, int, int] | None:
    """Var skiljer sig två bildrutor åt?

    Returnerar (x, y, bredd, höjd) med x och bredd justerade till jämn
    bytegräns, eller None om rutorna är identiska. Har vi ingen föregående ruta,
    eller har för mycket ändrats, returneras hela skärmen -- anroparen tolkar det
    som att det är dags för en full omritning.
    """
    full = (0, 0, PANEL_WIDTH, PANEL_HEIGHT)
    if previous is None:
        return full

    before = np.array(previous.convert("1"), dtype=bool)
    after = np.array(current.convert("1"), dtype=bool)
    if before.shape != after.shape:
        return full

    changed = before != after
    if not changed.any():
        return None

    rows = np.flatnonzero(changed.any(axis=1))
    cols = np.flatnonzero(changed.any(axis=0))
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(cols[0]), int(cols[-1]) + 1

    left -= left % X_ALIGNMENT
    if right % X_ALIGNMENT:
        right += X_ALIGNMENT - (right % X_ALIGNMENT)
    right = min(right, PANEL_WIDTH)

    area = (right - left) * (bottom - top)
    if area > PANEL_WIDTH * PANEL_HEIGHT * FULL_REDRAW_FRACTION:
        return full

    return (left, top, right - left, bottom - top)
