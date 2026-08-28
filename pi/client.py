"""Visningsklienten som körs på Raspberry Pi:n.

Den vet ingenting om väder, kalendrar eller skolmat. Den hämtar en bild, jämför
med den förra, och ritar om det som skiljer. All layout och all logik bor på
servern, och den här filen ska aldrig behöva ändras när tavlan ska se annorlunda
ut.

Hela poängen med uppdelningen: en layoutändring är en CSS-rad på servern, inte en
filöverföring till hallen.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.framebuffer import PANEL_HEIGHT, PANEL_WIDTH, dirty_region  # noqa: E402

from .epaper import Panel, open_panel  # noqa: E402

log = logging.getLogger("hallskarmen")

HTTP_TIMEOUT = 20.0

# Hur länge servern får vara tyst innan det märks ut på skärmen. Kortare än så
# och en omstart av servern skulle blinka till i hallen.
STALE_AFTER_SECONDS = 15 * 60

# Markören för "något är trasigt": en liten fyrkant uppe till höger. Ligger på
# jämn bytegräns, eftersom partiella uppdateringar packas åtta pixlar per byte.
MARKER = (PANEL_WIDTH - 16, 8, 8, 8)


class Client:
    """En hämtning, en jämförelse, en uppdatering. Inget tillstånd på disk."""

    def __init__(
        self,
        url: str,
        token: str,
        panel: Panel,
        *,
        stale_after: float = STALE_AFTER_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.panel = panel
        self.stale_after = stale_after
        self.session = session or requests.Session()

        self.previous: Image.Image | None = None
        self.etag: str | None = None
        self.marked_stale = False
        self.failures = 0

    def fetch(self) -> bytes | None:
        """Hämtar bilden. None betyder att servern svarat 'inget nytt'."""
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.etag:
            headers["If-None-Match"] = self.etag

        response = self.session.get(self.url, headers=headers, timeout=HTTP_TIMEOUT)
        if response.status_code == 304:
            return None
        response.raise_for_status()
        self.etag = response.headers.get("ETag") or self.etag
        return response.content

    def tick(self, now: datetime | None = None) -> str:
        """Ett varv. Returnerar vad som gjordes, för loggen och för testerna."""
        now = now or datetime.now()
        try:
            payload = self.fetch()
        except Exception:
            self.failures += 1
            log.warning("hämtningen misslyckades (%d i rad)", self.failures, exc_info=True)
            return self._maybe_mark_stale()

        self.failures = 0

        if payload is None:
            # Oförändrad bild. Inga partiella uppdateringar har skett sedan sist,
            # alltså har inga spökrester hunnit byggas upp -- panelen lämnas i fred.
            return self._recover() or "unchanged"

        image = Image.open(BytesIO(payload)).convert("1")
        if image.size != (PANEL_WIDTH, PANEL_HEIGHT):
            raise ValueError(f"servern skickade {image.size}, panelen är {PANEL_WIDTH}x{PANEL_HEIGHT}")

        region = dirty_region(self.previous, image)
        self.previous = image
        self.marked_stale = False

        if region is None:
            return "unchanged"

        full_screen = region == (0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        # Hel omritning varje hel timme. Partiella uppdateringar lämnar svaga
        # spökrester efter sig, och det här suddar bort dem.
        if full_screen or now.minute == 0:
            self.panel.show(image)
            return "full"

        self.panel.show_region(image, region)
        return "partial"

    def _maybe_mark_stale(self) -> str:
        """Markerar diskret att bilden inte längre är att lita på.

        Skärmen behåller sitt innehåll -- att tömma den vore sämre, eftersom
        gårdagens skolmat ändå är mer värd än en vit tavla. Men det ska gå att se
        skillnad på "inget nytt har hänt" och "något är trasigt".
        """
        if self.marked_stale or self.previous is None:
            return "error"
        if self.failures * 60 < self.stale_after:
            return "error"

        marked = self.previous.copy()
        x, y, width, height = MARKER
        ImageDraw.Draw(marked).rectangle([x, y, x + width - 1, y + height - 1], fill=0)
        self.panel.show_region(marked, MARKER)
        self.marked_stale = True
        return "marked-stale"

    def _recover(self) -> str | None:
        """Tar bort markeringen när servern svarar igen.

        Behövs eftersom servern kan svara 304 direkt efter att den kommit
        tillbaka -- bilden är ju densamma som innan den tystnade. Utan det här
        skulle markeringen bli kvar tills något faktiskt ändrades.
        """
        if not self.marked_stale or self.previous is None:
            return None
        self.panel.show(self.previous)
        self.marked_stale = False
        return "recovered"


def sleep_until_next_minute(offset: float = 2.0) -> None:
    """Sover till strax efter nästa minutskifte.

    Marginalen gör att servern hunnit rendera minuten som just började, så att
    klockan på väggen visar rätt siffra i stället för den förra.
    """
    now = time.time()
    time.sleep(max(0.5, (60 - now % 60) + offset))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visar hallskärmen.")
    parser.add_argument("--url", default=None, help="t.ex. https://din.server/dashboard.png")
    parser.add_argument("--token", default=None)
    parser.add_argument("--once", action="store_true", help="ett varv, sedan avsluta")
    parser.add_argument("--dry-run", action="store_true", help="rör inte panelen")
    parser.add_argument("--clear", action="store_true", help="rensa skärmen och avsluta")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import os

    url = args.url or os.environ.get("DASHBOARD_URL")
    token = args.token or os.environ.get("DASHBOARD_TOKEN")
    if not url or not token:
        parser.error("DASHBOARD_URL och DASHBOARD_TOKEN måste anges")

    panel = open_panel(dry_run=args.dry_run)
    if args.clear:
        panel.clear()
        panel.close()
        return 0

    client = Client(url, token, panel)
    try:
        while True:
            log.info("tick: %s", client.tick())
            if args.once:
                return 0
            sleep_until_next_minute()
    except KeyboardInterrupt:
        return 0
    finally:
        panel.close()


if __name__ == "__main__":
    raise SystemExit(main())
