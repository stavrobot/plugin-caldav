"""Tests for the free_busy tool.

The tool is loaded by path because tool directories are not packages. No CalDAV
server is contacted: the principal/calendars are fakes that return iCal fixture
text.
"""

import importlib.util
import inspect
import io
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SECRET = "SECRET"

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


def _ical(body: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )


def _athens_event(uid: str, start: str, end: str, extra: str = "") -> str:
    return _ical(
        ATHENS_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART;TZID=Europe/Athens:{start}\r\n"
        f"DTEND;TZID=Europe/Athens:{end}\r\n"
        f"{extra}"
        "END:VEVENT\r\n"
    )


class FakeEvent:
    def __init__(self, data: str) -> None:
        self.data = data


class FakeCalendar:
    def __init__(
        self,
        events: list[FakeEvent],
        name: str = "Personal",
        url: str = "https://caldav.example.com/calendars/user/personal/",
        components: tuple[str, ...] = ("VEVENT",),
        search_error: Exception | None = None,
        on_search: object = None,
    ) -> None:
        self._events = events
        self.name = name
        self.url = url
        self._components = list(components)
        self._search_error = search_error
        self._on_search = on_search
        self.search_args: tuple[object, object] | None = None
        self.search_calls = 0

    def get_supported_components(self) -> list[str]:
        return list(self._components)

    def search(self, *, start: object, end: object, event: bool) -> list[FakeEvent]:
        # Keyword-only, mirroring how caldav.Calendar.search consumes extra
        # arguments, so a positional call would bind to xml/server_expand there.
        self.search_calls += 1
        self.search_args = (start, end)
        if callable(self._on_search):
            self._on_search()
        if self._search_error is not None:
            raise self._search_error
        return self._events


class FakePrincipal:
    def __init__(self, calendars: list[FakeCalendar]) -> None:
        self._calendars = calendars

    def calendars(self) -> list[FakeCalendar]:
        return self._calendars


def _load_run() -> ModuleType:
    path = ROOT / "free_busy" / "run.py"
    spec = importlib.util.spec_from_file_location("free_busy_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    calendars: list[FakeCalendar],
    parameters: dict[str, str],
    config: dict[str, object] | None = None,
) -> tuple[str, str, object]:
    module = _load_run()
    monkeypatch.setattr(
        module.helpers, "get_principal", lambda: FakePrincipal(calendars)
    )
    monkeypatch.setattr(module.helpers, "load_config", lambda: dict(config or {}))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(parameters)))
    exit_code: object = 0
    try:
        module.main()
    except SystemExit as exception:
        exit_code = exception.code
    captured = capsys.readouterr()
    return captured.out, captured.err, exit_code


def _busy(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"start": start, "end": end} for start, end in items]


# --- output shape -----------------------------------------------------------


def test_output_has_only_busy_key_and_items_have_only_start_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_athens_event("e", "20260928T100000", "20260928T110000"))]
    )
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert err == ""
    result = json.loads(out)
    assert set(result) == {"busy"}
    assert len(result["busy"]) == 1
    assert set(result["busy"][0]) == {"start", "end"}


# --- time interpretation ----------------------------------------------------


def test_all_day_athens_is_local_midnight_to_next_midnight(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:allday\r\n"
        "DTSTART;VALUE=DATE:20260928\r\n"
        "DTEND;VALUE=DATE:20260929\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-30"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T00:00:00+03:00", "2026-09-29T00:00:00+03:00")
    )


def test_floating_event_uses_default_zone_wall_time(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:floating\r\n"
        "DTSTART:20260928T210000\r\n"
        "DTEND:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T21:00:00+03:00", "2026-09-28T22:00:00+03:00")
    )


def test_legacy_fixed_offset_tzid_keeps_instant(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:legacy\r\n"
        'DTSTART;TZID="UTC+03:00":20260928T210000\r\n'
        'DTEND;TZID="UTC+03:00":20260928T220000\r\n'
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T18:00:00+00:00", "2026-09-28T19:00:00+00:00")
    )


def test_unresolvable_tzid_uses_default_zone_wall_time(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:unknown-zone\r\n"
        "DTSTART;TZID=Custom/Zone:20260928T210000\r\n"
        "DTEND;TZID=Custom/Zone:20260928T220000\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T21:00:00+03:00", "2026-09-28T22:00:00+03:00")
    )


def test_timed_event_with_no_end_is_dropped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:noend\r\n"
        "DTSTART:20260928T100000\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == []


def test_duration_is_honoured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:duration\r\n"
        "DTSTART:20260928T100000\r\n"
        "DURATION:PT1H30M\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T10:00:00+00:00", "2026-09-28T11:30:00+00:00")
    )


# --- recurrence and status --------------------------------------------------


def test_recurrence_exdate_moved_override_and_cancelled_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        ATHENS_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:r\r\n"
        "DTSTART;TZID=Europe/Athens:20260901T100000\r\n"
        "DTEND;TZID=Europe/Athens:20260901T110000\r\n"
        "RRULE:FREQ=DAILY;COUNT=5\r\n"
        "EXDATE;TZID=Europe/Athens:20260903T100000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:r\r\n"
        "RECURRENCE-ID;TZID=Europe/Athens:20260902T100000\r\n"
        "DTSTART;TZID=Europe/Athens:20260902T150000\r\n"
        "DTEND;TZID=Europe/Athens:20260902T160000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:r\r\n"
        "RECURRENCE-ID;TZID=Europe/Athens:20260904T100000\r\n"
        "DTSTART;TZID=Europe/Athens:20260904T100000\r\n"
        "DTEND;TZID=Europe/Athens:20260904T110000\r\n"
        "STATUS:CANCELLED\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-01", "end": "2026-09-06"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-01T10:00:00+03:00", "2026-09-01T11:00:00+03:00"),
        ("2026-09-02T15:00:00+03:00", "2026-09-02T16:00:00+03:00"),
        ("2026-09-05T10:00:00+03:00", "2026-09-05T11:00:00+03:00"),
    )


def test_transparent_and_cancelled_are_skipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        "UID:t\r\n"
        "DTSTART:20260928T100000\r\n"
        "DTEND:20260928T110000\r\n"
        "TRANSP:TRANSPARENT\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:c\r\n"
        "DTSTART:20260928T120000\r\n"
        "DTEND:20260928T130000\r\n"
        "STATUS:CANCELLED\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == []


# --- merging and clipping ---------------------------------------------------


def test_overlapping_and_adjacent_intervals_merge_across_calendars(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="First",
        url="https://caldav.example.com/calendars/user/first/",
    )
    second = FakeCalendar(
        [
            FakeEvent(_athens_event("b", "20260928T110000", "20260928T120000")),
            FakeEvent(_athens_event("c", "20260928T113000", "20260928T123000")),
        ],
        name="Second",
        url="https://caldav.example.com/calendars/user/second/",
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [first, second],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T10:00:00+03:00", "2026-09-28T12:30:00+03:00")
    )


def test_intervals_are_clipped_to_the_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T090000", "20260928T100000"))]
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28T09:30:00", "end": "2026-09-28T09:45:00"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T09:30:00+03:00", "2026-09-28T09:45:00+03:00")
    )


# --- DST fall-back (Europe/Athens 2026-10-25 04:00+03:00 -> 03:00+02:00) ---


def _utc_event(uid: str, start: str, end: str) -> str:
    return _ical(
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{start}Z\r\n"
        f"DTEND:{end}Z\r\n"
        "END:VEVENT\r\n"
    )


def test_interval_crossing_the_rollback_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 00:30Z is 03:30+03:00 and 01:15Z is 03:15+02:00 across the rollback.
    calendar = FakeCalendar(
        [FakeEvent(_utc_event("a", "20261025T003000", "20261025T011500"))]
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-25", "end": "2026-10-26"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-10-25T03:30:00+03:00", "2026-10-25T03:15:00+02:00")
    )


def test_distinct_intervals_in_the_repeated_hour_are_not_merged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [
            FakeEvent(_utc_event("a", "20261025T003000", "20261025T004500")),
            FakeEvent(_utc_event("b", "20261025T013000", "20261025T014500")),
        ]
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-25", "end": "2026-10-26"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    # Same 03:30-03:45 wall clock, but one in +03:00 and one in +02:00.
    assert json.loads(out)["busy"] == _busy(
        ("2026-10-25T03:30:00+03:00", "2026-10-25T03:45:00+03:00"),
        ("2026-10-25T03:30:00+02:00", "2026-10-25T03:45:00+02:00"),
    )


def test_clipping_at_the_rollback_boundary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_utc_event("a", "20261025T003000", "20261025T020000"))]
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-25T01:00:00+00:00", "end": "2026-10-25T01:30:00+00:00"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-10-25T03:00:00+02:00", "2026-10-25T03:30:00+02:00")
    )


def test_range_spanning_the_rollback_is_accepted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar([])
    _, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-25", "end": "2026-10-26"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert calendar.search_calls == 1


def test_31_day_cap_measures_wall_clock_time_across_rollback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # October 1 to October 31 is exactly 31 wall-clock days in Athens, even
    # though the fall-back makes it 31 days and 1 hour of elapsed time.
    calendar = FakeCalendar([])
    _, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-01", "end": "2026-10-31"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert calendar.search_calls == 1


def test_32_day_wall_clock_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar([])
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-10-01", "end": "2026-11-01"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 1
    assert out == ""
    assert "31 days" in err
    assert calendar.search_calls == 0


def test_search_window_is_padded_by_one_day(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar([])
    _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert calendar.search_args is not None
    window_start, window_end = calendar.search_args
    # Bounds are UTC instants; 2026-09-28T00:00+03:00 is 2026-09-27T21:00Z.
    assert window_start == datetime(2026, 9, 26, 21, tzinfo=timezone.utc)
    assert window_end == datetime(2026, 9, 30, 21, tzinfo=timezone.utc)


def test_search_keywords_match_real_caldav_signature() -> None:
    """A positional call would bind to caldav's xml/server_expand arguments."""
    import caldav

    signature = inspect.signature(caldav.Calendar.search)
    start = datetime(2026, 9, 27, tzinfo=timezone.utc)
    end = datetime(2026, 9, 29, tzinfo=timezone.utc)

    bound = signature.bind(object(), start=start, end=end, event=True)

    assert "xml" not in bound.arguments
    assert "server_expand" not in bound.arguments
    assert bound.arguments["searchargs"] == {"start": start, "end": end, "event": True}

    # Sanity check that a positional call really would be swallowed.
    positional = signature.bind(object(), start, end)
    assert "xml" in positional.arguments
    assert "server_expand" in positional.arguments


# --- calendar selection -----------------------------------------------------


def test_name_and_contact_birthdays_url_exclusions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    birthday = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="birthdays",
        url="https://caldav.example.com/calendars/user/birthdays/",
    )
    contact = FakeCalendar(
        [FakeEvent(_athens_event("b", "20260928T100000", "20260928T110000"))],
        name="Contacts",
        url="https://caldav.example.com/calendars/user/contact_birthdays/",
    )
    personal = FakeCalendar(
        [FakeEvent(_athens_event("c", "20260928T120000", "20260928T130000"))],
        name="Personal",
        url="https://caldav.example.com/calendars/user/personal/",
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [birthday, contact, personal],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert birthday.search_calls == 0
    assert contact.search_calls == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T12:00:00+03:00", "2026-09-28T13:00:00+03:00")
    )


def test_excluded_names_are_trimmed_and_case_insensitive(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="Work",
        url="https://caldav.example.com/calendars/user/work/",
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {
            "default_timezone": "Europe/Athens",
            "freebusy_excluded_calendars": " work , Other ",
        },
    )

    assert code == 0
    assert calendar.search_calls == 0
    assert json.loads(out)["busy"] == []


def test_empty_exclusion_config_disables_name_exclusions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    birthday = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="Birthdays",
        url="https://caldav.example.com/calendars/user/birthdays/",
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [birthday],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens", "freebusy_excluded_calendars": ""},
    )

    assert code == 0
    assert birthday.search_calls == 1
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T10:00:00+03:00", "2026-09-28T11:00:00+03:00")
    )


def test_non_vevent_calendar_is_ignored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="Tasks",
        url="https://caldav.example.com/calendars/user/tasks/",
        components=("VTODO",),
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert calendar.search_calls == 0
    assert json.loads(out)["busy"] == []


# --- input validation -------------------------------------------------------


def test_date_only_end_covers_the_whole_day(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T230000", "20260928T233000"))]
    )
    out, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-28"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 0
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T23:00:00+03:00", "2026-09-28T23:30:00+03:00")
    )


@pytest.mark.parametrize(
    "start, end",
    [
        ("2026-09-28T10:00:00", "2026-09-28T10:00:00"),
        ("2026-09-28T10:00:00", "2026-09-28T09:00:00"),
        ("2026-09-29", "2026-09-28"),
    ],
)
def test_end_not_after_start_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    start: str,
    end: str,
) -> None:
    calendar = FakeCalendar([])
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": start, "end": end},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 1
    assert out == ""
    assert "end of the range must be after the start" in err
    assert calendar.search_calls == 0


def test_ranges_longer_than_31_days_are_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar([])
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-01-01T00:00:00", "end": "2026-02-02T00:00:00"},
        {"default_timezone": "UTC"},
    )

    assert code == 1
    assert out == ""
    assert "31 days" in err
    assert calendar.search_calls == 0


def test_exactly_31_days_is_allowed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar([])
    _, _, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-01-01T00:00:00", "end": "2026-02-01T00:00:00"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert calendar.search_calls == 1


# --- failure handling and leakage ------------------------------------------


def test_one_failing_calendar_fails_the_whole_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    good = FakeCalendar(
        [FakeEvent(_athens_event("a", "20260928T100000", "20260928T110000"))],
        name="Good",
        url="https://caldav.example.com/calendars/user/good/",
    )
    failing = FakeCalendar(
        [],
        name="Bad",
        url="https://caldav.example.com/calendars/user/bad/",
        search_error=RuntimeError(f"{SECRET} response body"),
    )
    out, err, code = _run(
        monkeypatch,
        capsys,
        [good, failing],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "Europe/Athens"},
    )

    assert code == 1
    assert out == ""
    assert err == "Failed to read calendars (RuntimeError)\n"
    assert SECRET not in err


def test_secret_is_absent_from_output_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "BEGIN:VEVENT\r\n"
        f"UID:{SECRET}-uid\r\n"
        f"SUMMARY:{SECRET} summary\r\n"
        f"DESCRIPTION:{SECRET} description\r\n"
        f"LOCATION:{SECRET} location\r\n"
        f"ATTENDEE:mailto:{SECRET}@example.com\r\n"
        f"ORGANIZER:mailto:{SECRET}@example.com\r\n"
        "DTSTART:20260928T100000\r\n"
        "DTEND:20260928T110000\r\n"
        "END:VEVENT\r\n"
    )
    calendar = FakeCalendar(
        [FakeEvent(_ical(body))],
        name=f"{SECRET} calendar",
        url="https://caldav.example.com/calendars/user/secret/",
    )
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert SECRET not in out
    assert SECRET not in err
    assert json.loads(out)["busy"] == _busy(
        ("2026-09-28T10:00:00+00:00", "2026-09-28T11:00:00+00:00")
    )


def test_secret_is_absent_from_output_on_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calendar = FakeCalendar(
        [],
        name=f"{SECRET} calendar",
        url="https://caldav.example.com/calendars/user/secret/",
        search_error=RuntimeError(f"{SECRET} response body"),
    )
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 1
    assert SECRET not in out
    assert SECRET not in err
    assert out == ""
    assert err == "Failed to read calendars (RuntimeError)\n"


def test_logging_and_warnings_are_suppressed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def noisy() -> None:
        logging.getLogger("caldav").warning(SECRET)
        warnings.warn(SECRET, stacklevel=1)

    calendar = FakeCalendar([], on_search=noisy)
    out, err, code = _run(
        monkeypatch,
        capsys,
        [calendar],
        {"start": "2026-09-28", "end": "2026-09-29"},
        {"default_timezone": "UTC"},
    )

    assert code == 0
    assert SECRET not in out
    assert SECRET not in err
