import pytest
from PIL import Image

from server.cache import TTLCache
from server.dashboard import build_context
from server.framebuffer import PANEL_HEIGHT, PANEL_WIDTH
from server.render.renderer import Renderer, render_html

CONTEXT = {
    "clock": "07:42",
    "date_line": "FREDAG 28 AUGUSTI",
    "departure_label": "MOT STAN",
    "stale": False,
    "weather": {
        "temperature": 14, "description": "Halvklart", "icon": "partly",
        "low": 11, "high": 19, "rain_at": "15:00",
    },
    "agenda": [
        {"time": "07:55", "title": "Ella — skolstart", "icon": "run"},
        {"time": "14:00", "title": "Tandläkare Otto", "icon": None},
    ],
    "meal": {"main": "Pasta arrabiata", "vegetarian": "Falafel med couscous"},
    "departures": [{"time": "07:51"}, {"time": "07:57"}],
    "almanac": {"name_day": "Gunnar, Gunder", "event": "1963 — Ett tal hålls"},
}


def test_every_field_reaches_the_page():
    html = render_html(CONTEXT)
    for expected in ("07:42", "FREDAG 28 AUGUSTI", "Pasta arrabiata", "MOT STAN", "07:51"):
        assert expected in html


def test_calendar_titles_cannot_inject_markup():
    """Kalendertitlar kommer utifrån och får inte kunna ändra sidan."""
    context = {**CONTEXT, "agenda": [{"time": "09:00", "title": "<script>fel()</script>", "icon": None}]}
    html = render_html(context)
    assert "<script>fel()</script>" not in html
    assert "&lt;script&gt;" in html


def test_an_empty_day_still_renders():
    context = {
        **CONTEXT, "agenda": [], "departures": [],
        "meal": {"main": None, "vegetarian": None},
        "almanac": {"name_day": None, "event": None},
        "weather": None,
    }
    assert "Inget inbokat" in render_html(context)


def test_the_stale_marker_only_appears_when_something_is_wrong():
    assert 'class="stale"' not in render_html(CONTEXT)
    assert 'class="stale"' in render_html({**CONTEXT, "stale": True})


def test_context_is_marked_stale_only_when_a_source_served_old_data(settings):
    cache = TTLCache()
    cache.get_or_fetch("weather", 0.0, lambda: {"temperature": 1})
    assert build_context(settings, cache)["stale"] is False

    def boom():
        raise RuntimeError("nere")

    cache.get_or_fetch("weather", 0.0, boom)
    assert build_context(settings, cache)["stale"] is True


@pytest.mark.slow
def test_the_screenshot_is_panel_shaped_and_has_no_grey():
    """Panelen har ingen gråskala. Allt som inte är svart eller vitt är en bugg."""
    image = Renderer().render_sync(CONTEXT)
    assert image.size == (PANEL_WIDTH, PANEL_HEIGHT)
    assert image.mode == "1"
    assert set(image.convert("L").getdata()) <= {0, 255}


@pytest.mark.slow
def test_two_different_days_produce_different_pictures():
    renderer = Renderer()
    morning = renderer.render_sync(CONTEXT)
    evening = renderer.render_sync({**CONTEXT, "clock": "18:05"})
    assert list(morning.getdata()) != list(evening.getdata())
