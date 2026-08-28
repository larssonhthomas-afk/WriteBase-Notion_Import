from datetime import datetime

import pytest
from PIL import Image

from pi.client import MARKER, Client
from pi.epaper import NullPanel, _resolve
from server.framebuffer import PANEL_HEIGHT, PANEL_WIDTH

from .conftest import as_png

AT_07_42 = datetime(2026, 8, 28, 7, 42)
ON_THE_HOUR = datetime(2026, 8, 28, 8, 0)


class Response:
    def __init__(self, status_code: int, content: bytes = b"", etag: str | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = {"ETag": etag} if etag else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Session:
    """Spelar upp ett förberett svar per anrop och sparar det som skickades."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append(headers or {})
        answer = self.script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def frames():
    white = Image.new("1", (PANEL_WIDTH, PANEL_HEIGHT), 1)
    nudged = white.copy()
    nudged.putpixel((100, 50), 0)
    black = Image.new("1", (PANEL_WIDTH, PANEL_HEIGHT), 0)
    return white, nudged, black


def build(script):
    panel = NullPanel()
    return Client("http://x/dashboard.png", "hemlis", panel, session=Session(script)), panel


def test_the_first_frame_redraws_the_whole_screen():
    white, _, _ = frames()
    client, panel = build([Response(200, as_png(white), '"a"')])
    assert client.tick(AT_07_42) == "full"
    assert panel.calls == [("show", (PANEL_WIDTH, PANEL_HEIGHT))]


def test_a_small_change_updates_only_that_patch():
    """Den tysta minutuppdateringen: klockan byts utan att skärmen blinkar."""
    white, nudged, _ = frames()
    client, panel = build([Response(200, as_png(white), '"a"'), Response(200, as_png(nudged), '"b"')])
    client.tick(AT_07_42)
    assert client.tick(AT_07_42) == "partial"
    assert panel.calls[-1][0] == "show_region"


def test_a_large_change_falls_back_to_a_full_redraw():
    white, _, black = frames()
    client, _ = build([Response(200, as_png(white), '"a"'), Response(200, as_png(black), '"b"')])
    client.tick(AT_07_42)
    assert client.tick(AT_07_42) == "full"


def test_the_whole_hour_forces_a_full_redraw():
    """Partiella uppdateringar lämnar spökrester. Timskiftet suddar dem."""
    white, nudged, _ = frames()
    client, _ = build([Response(200, as_png(white), '"a"'), Response(200, as_png(nudged), '"b"')])
    client.tick(AT_07_42)
    assert client.tick(ON_THE_HOUR) == "full"


def test_an_unchanged_image_leaves_the_panel_alone():
    white, _, _ = frames()
    client, panel = build([Response(200, as_png(white), '"a"'), Response(304)])
    client.tick(AT_07_42)
    before = len(panel.calls)
    assert client.tick(AT_07_42) == "unchanged"
    assert len(panel.calls) == before


def test_the_etag_is_sent_back_so_the_server_can_answer_304():
    white, _, _ = frames()
    client, _ = build([Response(200, as_png(white), '"a"'), Response(304)])
    client.tick(AT_07_42)
    client.tick(AT_07_42)
    assert client.session.requests[1]["If-None-Match"] == '"a"'


def test_a_failing_server_keeps_the_picture_on_the_wall():
    """Gårdagens skolmat är mer värd än en vit tavla."""
    white, _, _ = frames()
    client, panel = build([Response(200, as_png(white), '"a"'), RuntimeError("nere")])
    client.tick(AT_07_42)
    before = len(panel.calls)
    assert client.tick(AT_07_42) == "error"
    assert len(panel.calls) == before


def test_a_long_outage_is_marked_on_the_screen():
    white, _, _ = frames()
    script = [Response(200, as_png(white), '"a"')] + [RuntimeError("nere")] * 20
    client, panel = build(script)
    client.tick(AT_07_42)

    outcomes = [client.tick(AT_07_42) for _ in range(20)]
    assert "marked-stale" in outcomes
    assert outcomes.count("marked-stale") == 1, "markeringen ska ritas en gång, inte varje minut"
    assert panel.calls[-1] == ("show_region", MARKER)


def test_the_mark_is_removed_when_the_server_returns():
    """Servern svarar ofta 304 direkt efter att den kommit tillbaka."""
    white, _, _ = frames()
    script = [Response(200, as_png(white), '"a"')] + [RuntimeError("nere")] * 20 + [Response(304)]
    client, panel = build(script)
    client.tick(AT_07_42)
    for _ in range(20):
        client.tick(AT_07_42)

    assert client.tick(AT_07_42) == "recovered"
    assert client.marked_stale is False
    assert panel.calls[-1][0] == "show"


def test_a_wrongly_sized_image_is_refused():
    small = Image.new("1", (400, 240), 1)
    client, _ = build([Response(200, as_png(small), '"a"')])
    with pytest.raises(ValueError, match="800x480"):
        client.tick(AT_07_42)


def test_driver_method_names_are_resolved_across_versions():
    class OldDriver:
        def display_Part(self, *args):
            pass

    assert _resolve(OldDriver(), ("display_Partial", "display_Part")).__name__ == "display_Part"


def test_a_missing_driver_method_names_what_was_found():
    class Odd:
        def something_else(self):
            pass

    with pytest.raises(AttributeError, match="something_else"):
        _resolve(Odd(), ("display_Partial",))
