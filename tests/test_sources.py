from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from server.sources.agenda import load_provider, normalise, parse_ics, schedule_entries
from server.sources.almanac import pick_event
from server.sources.meals import parse_menu
from server.sources.transit import parse_departures
from server.sources.weather import parse_forecast

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def forecast(*entries):
    return {
        "timeSeries": [
            {
                "validTime": stamp,
                "parameters": [
                    {"name": "t", "values": [temperature]},
                    {"name": "Wsymb2", "values": [symbol]},
                    {"name": "pmean", "values": [rain]},
                ],
            }
            for stamp, temperature, symbol, rain in entries
        ]
    }


def test_weather_reads_current_conditions_and_span():
    payload = forecast(
        ("2026-08-28T05:00:00Z", 11.0, 4, 0.0),
        ("2026-08-28T13:00:00Z", 19.0, 19, 1.2),
    )
    result = parse_forecast(
        payload, now=datetime(2026, 8, 28, 5, tzinfo=timezone.utc), tz=STOCKHOLM
    )
    assert result["temperature"] == 11
    assert result["description"] == "Halvklart"
    assert result["icon"] == "partly"
    assert (result["low"], result["high"]) == (11, 19)


def test_weather_reports_rain_in_household_time_not_server_time():
    """En VPS står i UTC. Utan tidszon visar tavlan två timmar fel."""
    payload = forecast(("2026-08-28T13:00:00Z", 19.0, 19, 1.2))
    result = parse_forecast(
        payload, now=datetime(2026, 8, 28, 5, tzinfo=timezone.utc), tz=STOCKHOLM
    )
    assert result["rain_at"] == "15:00"


def test_weather_without_data_is_an_error_not_a_blank():
    with pytest.raises(ValueError):
        parse_forecast({"timeSeries": []})


MENU = """<rss><channel>
<item><title>Onsdag 27 augusti</title><description>Korv stroganoff</description></item>
<item><title>Fredag 28 augusti</title><description>Pasta arrabiata&lt;br/&gt;Vegetariskt: Falafel med couscous</description></item>
</channel></rss>"""


def test_menu_matches_on_the_date_not_on_list_order():
    result = parse_menu(MENU, today=date(2026, 8, 28))
    assert result["main"] == "Pasta arrabiata"
    assert result["vegetarian"] == "Falafel med couscous"


def test_menu_for_a_day_without_a_meal_is_empty():
    assert parse_menu(MENU, today=date(2026, 8, 30))["main"] is None


def departures(*items):
    return {
        "departures": [
            {"expected": stamp, "destination": destination, "line": {"designation": "14"}}
            for stamp, destination in items
        ]
    }


NOW = datetime.fromisoformat("2026-08-28T07:42:00+02:00")


def test_departures_are_shown_as_clock_times():
    """En nedräkning blir fel när skärmen inte uppdaterats på en kvart."""
    result = parse_departures(
        departures(("2026-08-28T07:51:00+02:00", "Kungsträdgården")), now=NOW, tz=STOCKHOLM
    )
    assert result[0]["time"] == "07:51"


def test_departures_you_cannot_reach_are_dropped():
    result = parse_departures(
        departures(
            ("2026-08-28T07:44:00+02:00", "Kungsträdgården"),
            ("2026-08-28T07:51:00+02:00", "Kungsträdgården"),
        ),
        walk_minutes=5,
        now=NOW,
        tz=STOCKHOLM,
    )
    assert [d["time"] for d in result] == ["07:51"]


def test_departures_are_filtered_by_direction():
    result = parse_departures(
        departures(
            ("2026-08-28T07:51:00+02:00", "Kungsträdgården"),
            ("2026-08-28T07:52:00+02:00", "Norsborg"),
        ),
        direction="Kungsträdgården",
        now=NOW,
        tz=STOCKHOLM,
    )
    assert [d["destination"] for d in result] == ["Kungsträdgården"]


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Stockholm:20260825T183000
RRULE:FREQ=WEEKLY;BYDAY=TU,TH
SUMMARY:Träning Ella
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;TZID=Europe/Stockholm:20260828T140000
SUMMARY:Tandläkare Otto
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART;VALUE=DATE:20260828
SUMMARY:Röd dag
END:VEVENT
END:VCALENDAR"""


def test_single_events_are_read(settings):
    events = parse_ics(ICS, day=date(2026, 8, 28), settings=settings)
    assert {"time": "14:00", "title": "Tandläkare Otto", "sort": 840} in events


def test_recurring_events_are_expanded(settings):
    """Träningen ligger som en upprepningsregel, inte som femtio poster."""
    thursday = parse_ics(ICS, day=date(2026, 8, 27), settings=settings)
    friday = parse_ics(ICS, day=date(2026, 8, 28), settings=settings)
    assert any(e["title"] == "Träning Ella" for e in thursday)
    assert not any(e["title"] == "Träning Ella" for e in friday)


def test_all_day_events_sort_first(settings):
    events = parse_ics(ICS, day=date(2026, 8, 28), settings=settings)
    whole_day = next(e for e in events if e["title"] == "Röd dag")
    assert whole_day["time"] is None
    assert whole_day["sort"] == -1


def test_school_start_is_marked_on_sports_days(settings):
    tuesday = schedule_entries(settings, date(2026, 8, 25))
    friday = schedule_entries(settings, date(2026, 8, 28))
    assert tuesday[0]["icon"] == "run"
    assert friday[0]["icon"] is None


def test_your_own_calendar_code_can_be_plugged_in(settings):
    """calendar_provider låter befintlig kod på servern mata skärmen direkt."""
    event = normalise(
        {"title": "Möte", "start": datetime(2026, 8, 28, 9, 0, tzinfo=STOCKHOLM)}, settings
    )
    assert event == {"time": "09:00", "title": "Möte", "icon": None, "sort": 540}


def test_provider_path_must_name_a_function():
    with pytest.raises(ValueError, match="modul:funktion"):
        load_provider("bara_en_modul")


def test_almanac_prefers_older_events():
    payload = {"events": [{"year": 2024, "text": "Nytt"}, {"year": 1963, "text": "Gammalt"}]}
    assert pick_event(payload) == "1963 — Gammalt"


def test_almanac_without_events_is_blank():
    assert pick_event({"events": []}) is None
