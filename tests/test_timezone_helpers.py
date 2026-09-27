from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import icalendar
import pytest

import helpers

ATHENS = ZoneInfo("Europe/Athens")

# A VTIMEZONE as clients commonly store it, so icalendar resolves Europe/Athens.
ATHENS_VTIMEZONE = (
    "BEGIN:VTIMEZONE\r\n"
    "TZID:Europe/Athens\r\n"
    "BEGIN:STANDARD\r\n"
    "DTSTART:19701025T040000\r\n"
    "TZOFFSETFROM:+0300\r\n"
    "TZOFFSETTO:+0200\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
    "TZNAME:EET\r\n"
    "END:STANDARD\r\n"
    "BEGIN:DAYLIGHT\r\n"
    "DTSTART:19700329T030000\r\n"
    "TZOFFSETFROM:+0200\r\n"
    "TZOFFSETTO:+0300\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
    "TZNAME:EEST\r\n"
    "END:DAYLIGHT\r\n"
    "END:VTIMEZONE\r\n"
)


def make_event(body: str) -> icalendar.cal.Component:
    ical = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )
    calendar = icalendar.Calendar.from_ical(ical)
    return next(c for c in calendar.walk() if c.name == "VEVENT")


# --- resolve_timezone -------------------------------------------------------


def test_resolve_timezone_explicit() -> None:
    assert helpers.resolve_timezone("Europe/Athens") == ATHENS


def test_resolve_timezone_uses_config_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        helpers, "load_config", lambda: {"default_timezone": "Europe/Athens"}
    )
    assert helpers.resolve_timezone() == ATHENS


def test_resolve_timezone_defaults_to_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers, "load_config", lambda: {})
    assert helpers.resolve_timezone() == ZoneInfo("UTC")


def test_resolve_timezone_invalid_exits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        helpers.resolve_timezone("Not/AZone")
    assert excinfo.value.code == 1
    assert "Invalid timezone: Not/AZone" in capsys.readouterr().err


# --- parse_datetime ---------------------------------------------------------


def test_parse_date_only_is_all_day() -> None:
    assert helpers.parse_datetime("2026-09-28", ATHENS) == date(2026, 9, 28)


def test_parse_bare_datetime_is_localized_in_zone() -> None:
    parsed = helpers.parse_datetime("2026-09-28T21:00:00", ATHENS)
    assert parsed == datetime(2026, 9, 28, 21, 0, tzinfo=ATHENS)
    assert parsed.tzinfo == ATHENS


def test_parse_offset_datetime_converts_to_zone() -> None:
    # 21:00+03:00 is the same instant as 18:00 UTC.
    parsed = helpers.parse_datetime("2026-09-28T21:00:00+03:00", ZoneInfo("UTC"))
    assert parsed == datetime(2026, 9, 28, 18, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_utc_z_datetime_converts_to_zone() -> None:
    parsed = helpers.parse_datetime("2026-09-28T18:00:00Z", ATHENS)
    assert parsed == datetime(2026, 9, 28, 21, 0, tzinfo=ATHENS)


def test_parse_bare_datetime_in_dst_gap_exits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 03:30 does not exist on the spring-forward day in Europe/Athens.
    with pytest.raises(SystemExit) as excinfo:
        helpers.parse_datetime("2026-03-29T03:30:00", ATHENS)

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "2026-03-29T03:30:00" in err
    assert "Europe/Athens" in err


def test_parse_ambiguous_fall_back_time_keeps_fold_zero() -> None:
    parsed = helpers.parse_datetime("2026-10-25T03:30:00", ATHENS)
    assert parsed == datetime(2026, 10, 25, 3, 30, tzinfo=ATHENS)
    assert parsed.fold == 0
    assert parsed.utcoffset() == timedelta(hours=3)


# --- reading and formatting stored properties -------------------------------


def test_read_zoned_with_vtimezone() -> None:
    component = make_event(
        ATHENS_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Europe/Athens:20260928T210000\r\n"
        "DTEND;TZID=Europe/Athens:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )
    parsed = helpers.read_property(component, "DTSTART")
    assert parsed is not None
    assert parsed.value == datetime(2026, 9, 28, 21, 0, tzinfo=ATHENS)
    assert parsed.tzid == "Europe/Athens"
    assert helpers.timezone_label(parsed) == "Europe/Athens"


@pytest.mark.parametrize(
    "body, expected_iso, expected_label",
    [
        # UTC "Z" value.
        (
            "DTSTART:20260928T180000Z\r\n",
            "2026-09-28T18:00:00+00:00",
            "UTC",
        ),
        # Floating time: no offset, no TZID.
        (
            "DTSTART:20260928T210000\r\n",
            "2026-09-28T21:00:00",
            "floating",
        ),
        # All-day value.
        (
            "DTSTART;VALUE=DATE:20260928\r\n",
            "2026-09-28",
            None,
        ),
        # Legacy fixed offset stored as a quoted TZID with no VTIMEZONE.
        (
            'DTSTART;TZID="UTC+03:00":20260928T210000\r\n',
            "2026-09-28T21:00:00+03:00",
            "UTC+03:00",
        ),
        # IANA TZID without a VTIMEZONE: icalendar resolves it via zoneinfo.
        (
            "DTSTART;TZID=Europe/Athens:20260928T210000\r\n",
            "2026-09-28T21:00:00+03:00",
            "Europe/Athens",
        ),
        # Unknown TZID with no VTIMEZONE: keep the naive value and raw TZID.
        (
            "DTSTART;TZID=Foo/Bar:20260928T210000\r\n",
            "2026-09-28T21:00:00",
            "Foo/Bar",
        ),
    ],
)
def test_format_property_labels(
    body: str, expected_iso: str, expected_label: str | None
) -> None:
    component = make_event(f"BEGIN:VEVENT\r\nUID:1\r\n{body}END:VEVENT\r\n")
    assert helpers.format_property(component, "DTSTART") == (
        expected_iso,
        expected_label,
    )


def test_read_legacy_offset_is_aware() -> None:
    component = make_event(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        'DTSTART;TZID="UTC+03:00":20260928T210000\r\n'
        "END:VEVENT\r\n"
    )
    parsed = helpers.read_property(component, "DTSTART")
    assert parsed is not None
    assert parsed.value.tzinfo == timezone(timedelta(hours=3))
    assert not parsed.is_floating


def test_read_unknown_tzid_stays_naive() -> None:
    component = make_event(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Foo/Bar:20260928T210000\r\n"
        "END:VEVENT\r\n"
    )
    parsed = helpers.read_property(component, "DTSTART")
    assert parsed is not None
    assert parsed.value.tzinfo is None
    assert parsed.tzid == "Foo/Bar"
    assert not parsed.is_floating


def test_read_floating_is_flagged() -> None:
    component = make_event(
        "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20260928T210000\r\nEND:VEVENT\r\n"
    )
    parsed = helpers.read_property(component, "DTSTART")
    assert parsed is not None
    assert parsed.is_floating


def test_format_missing_property_is_none() -> None:
    component = make_event(
        "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20260928T210000Z\r\nEND:VEVENT\r\n"
    )
    assert helpers.format_property(component, "DTEND") == (None, None)


# --- integration with icalendar serialization -------------------------------


def test_parsed_bare_datetime_serializes_with_tzid_and_vtimezone() -> None:
    start = helpers.parse_datetime("2026-09-28T21:00:00", ATHENS)
    end = helpers.parse_datetime("2026-09-28T22:00:00", ATHENS)

    calendar = icalendar.Calendar()
    calendar.add("PRODID", "-//caldav-plugin-tests//EN")
    calendar.add("VERSION", "2.0")
    event = icalendar.Event()
    event.add("UID", "1")
    event.add("DTSTART", start)
    event.add("DTEND", end)
    calendar.add_component(event)
    calendar.add_missing_timezones()

    serialized = calendar.to_ical()
    assert b"DTSTART;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"DTEND;TZID=Europe/Athens:20260928T220000" in serialized
    assert b"BEGIN:VTIMEZONE" in serialized
    assert b"TZID:Europe/Athens" in serialized
