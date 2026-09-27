import importlib.util
import io
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import icalendar
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# update_event/run.py is a standalone script, not a package module, and its
# main() only runs under __main__, so load it by path.
_SPEC = importlib.util.spec_from_file_location(
    "update_event_run", ROOT / "update_event" / "run.py"
)
assert _SPEC is not None and _SPEC.loader is not None
update_event = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(update_event)

UTC = ZoneInfo("UTC")

LONDON_VTIMEZONE = (
    "BEGIN:VTIMEZONE\r\n"
    "TZID:Europe/London\r\n"
    "BEGIN:STANDARD\r\n"
    "DTSTART:19701025T020000\r\n"
    "TZOFFSETFROM:+0100\r\n"
    "TZOFFSETTO:+0000\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
    "TZNAME:GMT\r\n"
    "END:STANDARD\r\n"
    "BEGIN:DAYLIGHT\r\n"
    "DTSTART:19700329T010000\r\n"
    "TZOFFSETFROM:+0000\r\n"
    "TZOFFSETTO:+0100\r\n"
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
    "TZNAME:BST\r\n"
    "END:DAYLIGHT\r\n"
    "END:VTIMEZONE\r\n"
)


def make_calendar(body: str):
    text = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )
    return icalendar.Calendar.from_ical(text)


# --- preserving the stored zone ---------------------------------------------


def test_updating_only_start_keeps_london_tzid_and_vtimezone() -> None:
    calendar = make_calendar(
        LONDON_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Europe/London:20260928T210000\r\n"
        "DTEND;TZID=Europe/London:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"start": "2026-09-29T21:00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DTSTART;TZID=Europe/London:20260929T210000" in serialized
    # The untouched end is re-expressed in the same zone, so it is unchanged.
    assert b"DTEND;TZID=Europe/London:20260928T220000" in serialized
    assert b"BEGIN:VTIMEZONE" in serialized
    assert b"TZID:Europe/London" in serialized


def test_new_offset_value_converts_to_existing_zone() -> None:
    calendar = make_calendar(
        LONDON_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Europe/London:20260928T210000\r\n"
        "DTEND;TZID=Europe/London:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )

    # 23:00+03:00 is the same instant as 21:00 BST.
    update_event.apply_update(
        calendar, {"start": "2026-09-29T23:00:00+03:00"}, UTC
    )
    serialized = calendar.to_ical()

    assert b"DTSTART;TZID=Europe/London:20260929T210000" in serialized


# --- switching and resolving the zone ---------------------------------------


def test_timezone_parameter_relocalizes_floating_event() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART:20260928T210000\r\n"
        "DTEND:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"timezone": "Europe/Athens"}, UTC)
    serialized = calendar.to_ical()

    # A floating event keeps its wall-clock time and gains the target zone.
    assert b"DTSTART;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"DTEND;TZID=Europe/Athens:20260928T220000" in serialized
    assert b"TZID:Europe/Athens" in serialized


def test_legacy_fixed_offset_keeps_instant_when_zoned() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        'DTSTART;TZID="UTC+03:00":20260928T210000\r\n'
        'DTEND;TZID="UTC+03:00":20260928T220000\r\n'
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"timezone": "UTC"}, ZoneInfo("Europe/Athens"))
    serialized = calendar.to_ical()

    assert b"DTSTART:20260928T180000Z" in serialized
    assert b"DTEND:20260928T190000Z" in serialized
    assert b"UTC+03:00" not in serialized


def test_default_zone_used_when_no_tzid_or_parameter() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART:20260928T210000\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"start": "2026-09-29T21:00:00"}, ZoneInfo("Europe/Athens"))
    serialized = calendar.to_ical()

    assert b"DTSTART;TZID=Europe/Athens:20260929T210000" in serialized


# --- all-day handling -------------------------------------------------------


def test_all_day_values_stay_untouched() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;VALUE=DATE:20260928\r\n"
        "DTEND;VALUE=DATE:20260929\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"timezone": "Europe/Athens"}, UTC)
    serialized = calendar.to_ical()

    assert b"DTSTART;VALUE=DATE:20260928" in serialized
    assert b"DTEND;VALUE=DATE:20260929" in serialized


def test_new_all_day_end_keeps_all_day() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;VALUE=DATE:20260928\r\n"
        "DTEND;VALUE=DATE:20260929\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"end": "2026-09-30"}, UTC)
    serialized = calendar.to_ical()

    assert b"DTSTART;VALUE=DATE:20260928" in serialized
    assert b"DTEND;VALUE=DATE:20260930" in serialized


def test_mixing_all_day_and_timed_exits(capsys: pytest.CaptureFixture[str]) -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;VALUE=DATE:20260928\r\n"
        "DTEND;VALUE=DATE:20260929\r\n"
        "END:VEVENT\r\n"
    )

    with pytest.raises(SystemExit) as excinfo:
        update_event.apply_update(calendar, {"start": "2026-09-28T21:00:00"}, UTC)

    assert excinfo.value.code == 1
    assert "mix all-day and timed" in capsys.readouterr().err


# --- DURATION-based events and non-time updates -----------------------------


def test_duration_based_event_keeps_duration_and_gets_no_dtend() -> None:
    calendar = make_calendar(
        LONDON_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Europe/London:20260928T210000\r\n"
        "DURATION:PT1H\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"start": "2026-09-29T21:00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DTSTART;TZID=Europe/London:20260929T210000" in serialized
    assert b"DURATION:PT1H" in serialized
    assert b"DTEND" not in serialized


def test_duration_based_event_gets_dtend_when_end_given() -> None:
    calendar = make_calendar(
        LONDON_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART;TZID=Europe/London:20260928T210000\r\n"
        "DURATION:PT1H\r\n"
        "END:VEVENT\r\n"
    )

    update_event.apply_update(calendar, {"end": "2026-09-28T23:00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DTEND;TZID=Europe/London:20260928T230000" in serialized
    # DTEND and DURATION must not coexist.
    assert b"DURATION" not in serialized


def test_summary_only_update_leaves_times_untouched() -> None:
    calendar = make_calendar(
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "SUMMARY:Old\r\n"
        "DTSTART:20260928T210000\r\n"
        "DTEND:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )

    component = update_event.apply_update(calendar, {"summary": "New"}, UTC)
    serialized = calendar.to_ical()

    assert str(component.get("SUMMARY")) == "New"
    assert b"DTSTART:20260928T210000" in serialized
    assert b"DTEND:20260928T220000" in serialized


# --- lazy default timezone resolution in main() -----------------------------


class FakeEvent:
    def __init__(self, data: str) -> None:
        self.data = data

    def save(self) -> None:
        pass


class FakeCalendar:
    def __init__(self, event: FakeEvent) -> None:
        self._event = event

    def event_by_uid(self, uid: str) -> FakeEvent:
        return self._event


def test_main_explicit_timezone_ignores_invalid_default_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # An invalid configured default must not break an update that carries an
    # explicit timezone: main() must not resolve the default unconditionally.
    monkeypatch.setattr(
        update_event.helpers,
        "load_config",
        lambda: {"default_timezone": "Not/AZone"},
    )
    monkeypatch.setattr(update_event.helpers, "get_principal", lambda: object())
    event = FakeEvent(
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:1\r\n"
        "DTSTART:20260928T210000\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    calendar = FakeCalendar(event)
    monkeypatch.setattr(
        update_event.helpers,
        "find_calendar_by_name",
        lambda principal, name: calendar,
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "calendar_name": "Personal",
                    "uid": "1",
                    "timezone": "Europe/Athens",
                }
            )
        ),
    )

    update_event.main()

    assert "DTSTART;TZID=Europe/Athens:20260928T210000" in event.data
    assert json.loads(capsys.readouterr().out)["uid"] == "1"
