"""Tests for the update_todo tool.

update_todo/run.py is a standalone script, not a package module, and its main()
only runs under __main__, so it is loaded by path. No CalDAV server is
contacted: helpers.load_config is monkeypatched and the principal/calendar
lookups are replaced with fakes.
"""

import importlib.util
import io
import json
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import icalendar
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "update_todo_run", ROOT / "update_todo" / "run.py"
)
assert _SPEC is not None and _SPEC.loader is not None
update_todo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(update_todo)

UTC = ZoneInfo("UTC")
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


def make_calendar(body: str):
    text = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )
    return icalendar.Calendar.from_ical(text)


# --- preserving / switching the stored zone ---------------------------------


def test_updating_due_keeps_existing_tzid_and_vtimezone() -> None:
    calendar = make_calendar(
        ATHENS_VTIMEZONE
        + "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "SUMMARY:Task\r\n"
        "DUE;TZID=Europe/Athens:20260928T210000\r\n"
        "DTSTART;TZID=Europe/Athens:20260928T200000\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"due": "2026-09-29T21:00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE;TZID=Europe/Athens:20260929T210000" in serialized
    # The untouched DTSTART is re-expressed in the same zone, so it is unchanged.
    assert b"DTSTART;TZID=Europe/Athens:20260928T200000" in serialized
    assert b"BEGIN:VTIMEZONE" in serialized
    assert b"TZID:Europe/Athens" in serialized


def test_new_offset_due_converts_to_existing_zone() -> None:
    calendar = make_calendar(
        ATHENS_VTIMEZONE
        + "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DUE;TZID=Europe/Athens:20260928T210000\r\n"
        "END:VTODO\r\n"
    )

    # 18:00Z is the same instant as 21:00 EEST.
    update_todo.apply_update(calendar, {"due": "2026-09-29T18:00:00+00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE;TZID=Europe/Athens:20260929T210000" in serialized


def test_timezone_parameter_relocalizes_floating_todo() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DUE:20260928T210000\r\n"
        "DTSTART:20260928T200000\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"timezone": "Europe/Athens"}, UTC)
    serialized = calendar.to_ical()

    # A floating value keeps its wall-clock time and gains the target zone.
    assert b"DUE;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"DTSTART;TZID=Europe/Athens:20260928T200000" in serialized
    assert b"TZID:Europe/Athens" in serialized


def test_legacy_fixed_offset_keeps_instant_when_zoned() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        'DUE;TZID="UTC+03:00":20260928T210000\r\n'
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"timezone": "UTC"}, ATHENS)
    serialized = calendar.to_ical()

    assert b"DUE:20260928T180000Z" in serialized
    assert b"UTC+03:00" not in serialized


def test_default_zone_used_when_no_tzid_or_parameter() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\nUID:1\r\nDUE:20260928T210000\r\nEND:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"due": "2026-09-29T21:00:00"}, ATHENS)
    serialized = calendar.to_ical()

    assert b"DUE;TZID=Europe/Athens:20260929T210000" in serialized


def test_all_day_due_stays_untouched_with_timezone() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\nUID:1\r\nDUE;VALUE=DATE:20260928\r\nEND:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"timezone": "Europe/Athens"}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE;VALUE=DATE:20260928" in serialized


def test_mixing_all_day_due_and_timed_start_exits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DUE;VALUE=DATE:20260928\r\n"
        "DTSTART:20260928T210000\r\n"
        "END:VTODO\r\n"
    )

    with pytest.raises(SystemExit) as excinfo:
        update_todo.apply_update(calendar, {"timezone": "Europe/Athens"}, UTC)

    assert excinfo.value.code == 1
    assert "mix all-day and timed" in capsys.readouterr().err


# --- removing DUE and DURATION ----------------------------------------------


def test_due_null_removes_due_and_leaves_start_alone() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DUE:20260928T210000\r\n"
        "DTSTART:20260928T200000\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"due": None}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE" not in serialized
    # Without an explicit timezone, DTSTART is not touched at all.
    assert b"DTSTART:20260928T200000" in serialized
    assert b"TZID" not in serialized


def test_due_null_with_timezone_rewrites_start() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DUE:20260928T210000\r\n"
        "DTSTART:20260928T200000\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"due": None, "timezone": "Europe/Athens"}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE" not in serialized
    assert b"DTSTART;TZID=Europe/Athens:20260928T200000" in serialized


def test_setting_due_removes_duration() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "DTSTART:20260928T200000\r\n"
        "DURATION:PT1H\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"due": "2026-09-28T21:00:00"}, UTC)
    serialized = calendar.to_ical()

    assert b"DUE:20260928T210000Z" in serialized
    assert b"DURATION" not in serialized


# --- status handling ---------------------------------------------------------


def test_status_completed_stamps_completed_utc_when_absent() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\nUID:1\r\nSTATUS:NEEDS-ACTION\r\nEND:VTODO\r\n"
    )

    component = update_todo.apply_update(calendar, {"status": "COMPLETED"}, UTC)
    completed = component.get("COMPLETED")

    assert str(component.get("STATUS")) == "COMPLETED"
    assert completed is not None
    assert completed.dt.utcoffset() == timedelta(0)
    assert b"COMPLETED:" in calendar.to_ical()


def test_status_completed_keeps_existing_completed_timestamp() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "STATUS:NEEDS-ACTION\r\n"
        "COMPLETED:20260101T000000Z\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"status": "COMPLETED"}, UTC)
    serialized = calendar.to_ical()

    assert b"COMPLETED:20260101T000000Z" in serialized


def test_non_completed_status_clears_completed_and_full_percent() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "STATUS:COMPLETED\r\n"
        "COMPLETED:20260101T000000Z\r\n"
        "PERCENT-COMPLETE:100\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"status": "CANCELLED"}, UTC)
    serialized = calendar.to_ical()

    assert b"STATUS:CANCELLED" in serialized
    assert b"COMPLETED" not in serialized
    assert b"PERCENT-COMPLETE" not in serialized


def test_non_completed_status_keeps_partial_percent() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "STATUS:COMPLETED\r\n"
        "COMPLETED:20260101T000000Z\r\n"
        "PERCENT-COMPLETE:50\r\n"
        "END:VTODO\r\n"
    )

    update_todo.apply_update(calendar, {"status": "NEEDS-ACTION"}, UTC)
    serialized = calendar.to_ical()

    assert b"STATUS:NEEDS-ACTION" in serialized
    assert b"COMPLETED" not in serialized
    assert b"PERCENT-COMPLETE:50" in serialized


def test_invalid_status_exits(capsys: pytest.CaptureFixture[str]) -> None:
    calendar = make_calendar("BEGIN:VTODO\r\nUID:1\r\nEND:VTODO\r\n")

    with pytest.raises(SystemExit) as excinfo:
        update_todo.apply_update(calendar, {"status": "DONE"}, UTC)

    assert excinfo.value.code == 1
    assert "Invalid status: DONE" in capsys.readouterr().err


# --- priority and other scalar fields ---------------------------------------


def test_priority_is_set() -> None:
    calendar = make_calendar("BEGIN:VTODO\r\nUID:1\r\nEND:VTODO\r\n")

    update_todo.apply_update(calendar, {"priority": 3}, UTC)

    assert b"PRIORITY:3" in calendar.to_ical()


@pytest.mark.parametrize("priority", [-1, 10, "high"])
def test_invalid_priority_exits(
    priority: object, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = make_calendar("BEGIN:VTODO\r\nUID:1\r\nEND:VTODO\r\n")

    with pytest.raises(SystemExit) as excinfo:
        update_todo.apply_update(calendar, {"priority": priority}, UTC)

    assert excinfo.value.code == 1
    assert "Invalid priority" in capsys.readouterr().err


def test_only_given_fields_change() -> None:
    calendar = make_calendar(
        "BEGIN:VTODO\r\n"
        "UID:1\r\n"
        "SUMMARY:Old\r\n"
        "DESCRIPTION:Old body\r\n"
        "DUE:20260928T180000Z\r\n"
        "END:VTODO\r\n"
    )

    component = update_todo.apply_update(calendar, {"summary": "New"}, UTC)
    serialized = calendar.to_ical()

    assert str(component.get("SUMMARY")) == "New"
    assert str(component.get("DESCRIPTION")) == "Old body"
    assert b"DUE:20260928T180000Z" in serialized


# --- main() wiring -----------------------------------------------------------


class FakeTodo:
    def __init__(self, data: str) -> None:
        self.data = data
        self.saved = False

    def save(self) -> None:
        self.saved = True


class FakeCalendar:
    def __init__(self, todo: FakeTodo) -> None:
        self._todo = todo

    def todo_by_uid(self, uid: str) -> FakeTodo:
        return self._todo


TODO_DATA = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//caldav-plugin-tests//EN\r\n"
    "BEGIN:VTODO\r\n"
    "UID:1\r\n"
    "SUMMARY:Task\r\n"
    "DUE:20260928T210000\r\n"
    "END:VTODO\r\n"
    "END:VCALENDAR\r\n"
)


def patch_calendar(monkeypatch: pytest.MonkeyPatch, todo: FakeTodo) -> None:
    monkeypatch.setattr(update_todo.helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        update_todo.helpers,
        "find_calendar_by_name",
        lambda principal, name: FakeCalendar(todo),
    )


def test_main_saves_and_reports_uid_and_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    todo = FakeTodo(TODO_DATA)
    patch_calendar(monkeypatch, todo)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "calendar_name": "Personal",
                    "uid": "1",
                    "due": "2026-09-29T21:00:00",
                    "timezone": "Europe/Athens",
                }
            )
        ),
    )

    update_todo.main()

    assert todo.saved is True
    assert "DUE;TZID=Europe/Athens:20260929T210000" in todo.data
    assert json.loads(capsys.readouterr().out) == {"uid": "1", "summary": "Task"}


def test_main_explicit_timezone_ignores_invalid_default_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An invalid configured default must not break an update that carries an
    # explicit timezone: main() must not resolve the default unconditionally.
    monkeypatch.setattr(
        update_todo.helpers,
        "load_config",
        lambda: {"default_timezone": "Not/AZone"},
    )
    todo = FakeTodo(TODO_DATA)
    patch_calendar(monkeypatch, todo)
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

    update_todo.main()

    assert "DUE;TZID=Europe/Athens:20260928T210000" in todo.data
    assert json.loads(capsys.readouterr().out)["uid"] == "1"


def test_main_rejects_unknown_parameters(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps({"calendar_name": "Personal", "uid": "1", "bogus": True})
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        update_todo.main()

    assert excinfo.value.code == 1
    assert "Unknown parameters: bogus" in capsys.readouterr().err
