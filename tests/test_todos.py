"""Tests for create_todo/list_todos timezone handling for due dates.

The two tools are loaded by path because their directories are not packages.
No CalDAV server is contacted: the principal/calendar lookups are replaced
with fakes, and the DUE values are exercised as iCal fixture text.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import helpers
import pytest

ROOT = Path(__file__).resolve().parent.parent
ATHENS = ZoneInfo("Europe/Athens")
ATHENS_VTIMEZONE_MARKER = b"TZID:Europe/Athens"

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


def _load_run(tool: str) -> ModuleType:
    path = ROOT / tool / "run.py"
    spec = importlib.util.spec_from_file_location(f"{tool}_run", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ical(body: str) -> str:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//caldav-plugin-tests//EN\r\n"
        f"{body}"
        "END:VCALENDAR\r\n"
    )


def use_default_timezone(monkeypatch: pytest.MonkeyPatch, timezone_name: str) -> None:
    monkeypatch.setattr(
        helpers, "load_config", lambda: {"default_timezone": timezone_name}
    )


# --- create_todo: building the DUE property ---------------------------------


def make_parameters(**overrides: object) -> dict[str, object]:
    parameters: dict[str, object] = {"summary": "Buy milk"}
    parameters.update(overrides)
    return parameters


def test_bare_due_uses_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_default_timezone(monkeypatch, "Europe/Athens")
    create_todo = _load_run("create_todo")

    calendar, uid = create_todo.build_calendar(
        make_parameters(due="2026-09-28T21:00:00")
    )

    serialized = calendar.to_ical()
    assert b"DUE;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"BEGIN:VTIMEZONE" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized
    assert uid in serialized.decode("utf-8")


def test_offset_due_matches_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 21:00+03:00 is the same instant as 21:00 Europe/Athens in September.
    use_default_timezone(monkeypatch, "Europe/Athens")
    create_todo = _load_run("create_todo")

    calendar, _ = create_todo.build_calendar(
        make_parameters(due="2026-09-28T21:00:00+03:00")
    )

    serialized = calendar.to_ical()
    assert b"DUE;TZID=Europe/Athens:20260928T210000" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized


def test_explicit_timezone_overrides_config_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_default_timezone(monkeypatch, "UTC")
    create_todo = _load_run("create_todo")

    calendar, _ = create_todo.build_calendar(
        make_parameters(due="2026-09-28T21:00:00", timezone="Europe/Athens")
    )

    serialized = calendar.to_ical()
    assert b"DUE;TZID=Europe/Athens:20260928T210000" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized


def test_bare_due_without_config_timezone_uses_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers, "load_config", lambda: {})
    create_todo = _load_run("create_todo")

    calendar, _ = create_todo.build_calendar(
        make_parameters(due="2026-09-28T21:00:00")
    )

    # icalendar renders a UTC value with the Z suffix rather than a TZID.
    serialized = calendar.to_ical()
    assert b"DUE:20260928T210000Z" in serialized


def test_date_only_due_is_all_day(monkeypatch: pytest.MonkeyPatch) -> None:
    use_default_timezone(monkeypatch, "Europe/Athens")
    create_todo = _load_run("create_todo")

    calendar, _ = create_todo.build_calendar(make_parameters(due="2026-09-28"))

    serialized = calendar.to_ical()
    assert b"DUE;VALUE=DATE:20260928" in serialized
    assert b"BEGIN:VTIMEZONE" not in serialized


def test_due_omitted_leaves_due_out_and_skips_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An absent due value must not require (or validate) any timezone config.
    def _unexpected_load() -> dict[str, object]:
        raise AssertionError("load_config should not be called without a due value")

    monkeypatch.setattr(helpers, "load_config", _unexpected_load)
    create_todo = _load_run("create_todo")

    calendar, _ = create_todo.build_calendar(make_parameters())

    assert b"DUE" not in calendar.to_ical()


# --- create_todo: main wiring -----------------------------------------------


class FakeTodoCalendar:
    def __init__(self) -> None:
        self.payload: str | None = None

    def save_todo(self, payload: str) -> None:
        self.payload = payload


def test_create_todo_main_accepts_timezone_and_serializes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_todo = _load_run("create_todo")
    fake_calendar = FakeTodoCalendar()
    use_default_timezone(monkeypatch, "UTC")
    monkeypatch.setattr(helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        helpers, "find_calendar_by_name", lambda principal, name: fake_calendar
    )

    payload = {
        "calendar_name": "Personal",
        "summary": "Buy milk",
        "due": "2026-09-28T21:00:00",
        "timezone": "Europe/Athens",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    create_todo.main()

    assert fake_calendar.payload is not None
    assert "DUE;TZID=Europe/Athens:20260928T210000" in fake_calendar.payload
    result = json.loads(capsys.readouterr().out)
    assert result["summary"] == "Buy milk"
    assert result["uid"]


# --- list_todos: DUE formatting and timezone labels -------------------------

# label, VTODO body, expected due, expected timezone.
CASES = [
    (
        "zoned",
        ATHENS_VTIMEZONE
        + "BEGIN:VTODO\r\n"
        "UID:zoned\r\n"
        "SUMMARY:Zoned\r\n"
        "DUE;TZID=Europe/Athens:20260928T210000\r\n"
        "END:VTODO\r\n",
        "2026-09-28T21:00:00+03:00",
        "Europe/Athens",
    ),
    (
        "floating",
        "BEGIN:VTODO\r\n"
        "UID:floating\r\n"
        "SUMMARY:Floating\r\n"
        "DUE:20260928T210000\r\n"
        "END:VTODO\r\n",
        "2026-09-28T21:00:00",
        "floating",
    ),
    (
        "utc",
        "BEGIN:VTODO\r\n"
        "UID:utc\r\n"
        "SUMMARY:Utc\r\n"
        "DUE:20260928T180000Z\r\n"
        "END:VTODO\r\n",
        "2026-09-28T18:00:00+00:00",
        "UTC",
    ),
    (
        "legacy-offset",
        "BEGIN:VTODO\r\n"
        "UID:legacy\r\n"
        "SUMMARY:Legacy\r\n"
        'DUE;TZID="UTC+03:00":20260928T210000\r\n'
        "END:VTODO\r\n",
        "2026-09-28T21:00:00+03:00",
        "UTC+03:00",
    ),
    (
        "all-day",
        "BEGIN:VTODO\r\n"
        "UID:allday\r\n"
        "SUMMARY:All day\r\n"
        "DUE;VALUE=DATE:20260928\r\n"
        "END:VTODO\r\n",
        "2026-09-28",
        None,
    ),
    (
        "unknown-tzid",
        "BEGIN:VTODO\r\n"
        "UID:unknown\r\n"
        "SUMMARY:Unknown\r\n"
        "DUE;TZID=Foo/Bar:20260928T210000\r\n"
        "END:VTODO\r\n",
        "2026-09-28T21:00:00",
        "Foo/Bar",
    ),
]

CASE_IDS = [case[0] for case in CASES]


class FakeTodo:
    def __init__(self, data: str) -> None:
        self.data = data


class FakeListCalendar:
    def __init__(self, todos: list[FakeTodo]) -> None:
        self._todos = todos

    def todos(self, include_completed: bool = False) -> list[FakeTodo]:
        assert include_completed is True
        return self._todos


def _run_list_tool(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    calendar: FakeListCalendar,
    parameters: dict[str, object],
) -> object:
    module = _load_run("list_todos")
    monkeypatch.setattr(module.helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        module.helpers,
        "find_calendar_by_name",
        lambda principal, name: calendar,
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(parameters)))
    module.main()
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("label, body, due, tz", CASES, ids=CASE_IDS)
def test_list_todos_reports_offsets_and_timezone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    body: str,
    due: str,
    tz: str | None,
) -> None:
    calendar = FakeListCalendar([FakeTodo(_ical(body))])
    output = _run_list_tool(
        monkeypatch, capsys, calendar, {"calendar_name": "Personal"}
    )

    assert isinstance(output, list) and len(output) == 1
    assert output[0]["due"] == due
    assert output[0]["timezone"] == tz


def test_list_todos_missing_due_is_null(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calendar = FakeListCalendar(
        [
            FakeTodo(
                _ical(
                    "BEGIN:VTODO\r\n"
                    "UID:none\r\n"
                    "SUMMARY:No due\r\n"
                    "END:VTODO\r\n"
                )
            )
        ]
    )
    output = _run_list_tool(
        monkeypatch, capsys, calendar, {"calendar_name": "Personal"}
    )

    assert output[0]["due"] is None
    assert output[0]["timezone"] is None


def test_list_todos_keeps_other_fields_and_filters_by_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calendar = FakeListCalendar(
        [
            FakeTodo(
                _ical(
                    "BEGIN:VTODO\r\n"
                    "UID:open\r\n"
                    "SUMMARY:Open\r\n"
                    "STATUS:NEEDS-ACTION\r\n"
                    "PRIORITY:3\r\n"
                    "DESCRIPTION:Something to do\r\n"
                    "DUE:20260928T180000Z\r\n"
                    "END:VTODO\r\n"
                )
            ),
            FakeTodo(
                _ical(
                    "BEGIN:VTODO\r\n"
                    "UID:done\r\n"
                    "SUMMARY:Done\r\n"
                    "STATUS:COMPLETED\r\n"
                    "END:VTODO\r\n"
                )
            ),
        ]
    )
    output = _run_list_tool(
        monkeypatch,
        capsys,
        calendar,
        {"calendar_name": "Personal", "status": "NEEDS-ACTION"},
    )

    assert isinstance(output, list) and len(output) == 1
    assert output[0] == {
        "uid": "open",
        "summary": "Open",
        "due": "2026-09-28T18:00:00+00:00",
        "timezone": "UTC",
        "status": "NEEDS-ACTION",
        "description": "Something to do",
        "priority": "3",
    }
