from datetime import datetime
from zoneinfo import ZoneInfo

from server.clock import format_date, now, to_local, weekday_key


def test_the_header_reads_as_swedish_prose(settings):
    assert format_date(datetime(2026, 8, 28)) == "FREDAG 28 AUGUSTI"


def test_the_clock_follows_the_household_not_the_server(settings):
    """Servern är en VPS i UTC. Tavlan hänger i Stockholm."""
    utc_noon = datetime(2026, 8, 28, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert to_local(utc_noon, settings).strftime("%H:%M") == "14:00"


def test_naive_times_are_read_as_household_time(settings):
    assert to_local(datetime(2026, 8, 28, 14, 0), settings).hour == 14


def test_now_is_timezone_aware(settings):
    assert now(settings).tzinfo is not None


def test_schedule_weekdays_use_the_short_swedish_keys():
    assert weekday_key(datetime(2026, 8, 25)) == "tis"
    assert weekday_key(datetime(2026, 8, 28)) == "fre"
