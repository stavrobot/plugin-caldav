"""Tests for list_events/get_event output formatting.

The two tools are loaded by path because their directories are not packages.
No CalDAV server is contacted: the principal/calendar lookups are replaced
with fakes that return iCal fixture text.
"""

import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
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


def _ical(body: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )


# label, VEVENT body, expected start, expected end, expected timezone.
CASES = [
    (
        "zoned",
        ATHENS_VTIMEZONE
        + "BEGIN:VEVENT\r\n"
        "UID:zoned\r\n"
        "SUMMARY:Zoned\r\n"
        "DTSTART;TZID=Europe/Athens:20260928T210000\r\n"
        "DTEND;TZID=Europe/Athens:20260928T220000\r\n"
        "END:VEVENT\r\n",
        "2026-09-28T21:00:00+03:00",
        "2026-09-28T22:00:00+03:00",
        "Europe/Athens",
    ),
    (
        "floating",
        "BEGIN:VEVENT\r\n"
        "UID:floating\r\n"
        "SUMMARY:Floating\r\n"
        "DTSTART:20260928T210000\r\n"
        "DTEND:20260928T220000\r\n"
        "END:VEVENT\r\n",
        "2026-09-28T21:00:00",
        "2026-09-28T22:00:00",
        "floating",
    ),
    (
        "utc",
        "BEGIN:VEVENT\r\n"
        "UID:utc\r\n"
        "SUMMARY:Utc\r\n"
        "DTSTART:20260928T180000Z\r\n"
        "DTEND:20260928T190000Z\r\n"
        "END:VEVENT\r\n",
        "2026-09-28T18:00:00+00:00",
        "2026-09-28T19:00:00+00:00",
        "UTC",
    ),
    (
        "legacy-offset",
        "BEGIN:VEVENT\r\n"
        "UID:legacy\r\n"
        "SUMMARY:Legacy\r\n"
        'DTSTART;TZID="UTC+03:00":20260928T210000\r\n'
        'DTEND;TZID="UTC+03:00":20260928T220000\r\n'
        "END:VEVENT\r\n",
        "2026-09-28T21:00:00+03:00",
        "2026-09-28T22:00:00+03:00",
        "UTC+03:00",
    ),
    (
        "all-day",
        "BEGIN:VEVENT\r\n"
        "UID:allday\r\n"
        "SUMMARY:All day\r\n"
        "DTSTART;VALUE=DATE:20260928\r\n"
        "DTEND;VALUE=DATE:20260929\r\n"
        "END:VEVENT\r\n",
        "2026-09-28",
        "2026-09-29",
        None,
    ),
]

CASE_IDS = [case[0] for case in CASES]


class FakeEvent:
    def __init__(self, data: str) -> None:
        self.data = data


class FakeCalendar:
    def __init__(self, events: list[FakeEvent]) -> None:
        self._events = events
        self.search_args: tuple[object, object] | None = None

    def events(self) -> list[FakeEvent]:
        return self._events

    def date_search(self, start: object, end: object) -> list[FakeEvent]:
        self.search_args = (start, end)
        return self._events

    def event_by_uid(self, uid: str) -> FakeEvent:
        return self._events[0]


def _load_run(tool: str) -> ModuleType:
    path = ROOT / tool / "run.py"
    spec = importlib.util.spec_from_file_location(f"{tool}_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_tool(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool: str,
    calendar: FakeCalendar,
    parameters: dict[str, str],
    config: dict[str, str],
) -> object:
    module = _load_run(tool)
    monkeypatch.setattr(module.helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        module.helpers,
        "find_calendar_by_name",
        lambda principal, name: calendar,
    )
    monkeypatch.setattr(module.helpers, "load_config", lambda: config)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(parameters)))
    module.main()
    return json.loads(capsys.readouterr().out)


# --- list_events ------------------------------------------------------------


@pytest.mark.parametrize("label, body, start, end, tz", CASES, ids=CASE_IDS)
def test_list_events_reports_offsets_and_timezone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    body: str,
    start: str,
    end: str,
    tz: str | None,
) -> None:
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    output = _run_tool(
        monkeypatch, capsys, "list_events", calendar, {"calendar_name": "Personal"}, {}
    )

    assert isinstance(output, list) and len(output) == 1
    assert output[0]["start"] == start
    assert output[0]["end"] == end
    assert output[0]["timezone"] == tz


# --- get_event --------------------------------------------------------------


@pytest.mark.parametrize("label, body, start, end, tz", CASES, ids=CASE_IDS)
def test_get_event_reports_offsets_and_timezone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    body: str,
    start: str,
    end: str,
    tz: str | None,
) -> None:
    calendar = FakeCalendar([FakeEvent(_ical(body))])
    output = _run_tool(
        monkeypatch,
        capsys,
        "get_event",
        calendar,
        {"calendar_name": "Personal", "uid": "1"},
        {},
    )

    assert isinstance(output, dict)
    assert output["start"] == start
    assert output["end"] == end
    assert output["timezone"] == tz


# --- list_events range filter ----------------------------------------------


@pytest.mark.parametrize(
    "config, start_input, end_input, expected_start, expected_end",
    [
        # Bare range values use the configured default timezone.
        (
            {"default_timezone": "Europe/Athens"},
            "2026-09-28T21:00:00",
            "2026-09-28T22:00:00",
            datetime(2026, 9, 28, 21, 0, tzinfo=ATHENS),
            datetime(2026, 9, 28, 22, 0, tzinfo=ATHENS),
        ),
        # ... and fall back to UTC when unset.
        (
            {},
            "2026-09-28T21:00:00",
            "2026-09-28T22:00:00",
            datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc),
        ),
        # Offset range values keep the instant, expressed in the target zone.
        (
            {"default_timezone": "UTC"},
            "2026-09-28T21:00:00+03:00",
            "2026-09-28T22:00:00+03:00",
            datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_list_events_range_values_are_timezone_aware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config: dict[str, str],
    start_input: str,
    end_input: str,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    calendar = FakeCalendar([FakeEvent(_ical(CASES[2][1]))])
    _run_tool(
        monkeypatch,
        capsys,
        "list_events",
        calendar,
        {"calendar_name": "Personal", "start": start_input, "end": end_input},
        config,
    )

    assert calendar.search_args is not None
    recorded_start, recorded_end = calendar.search_args
    assert recorded_start == expected_start
    assert recorded_start.tzinfo is not None
    assert recorded_end == expected_end
    assert recorded_end.tzinfo is not None
