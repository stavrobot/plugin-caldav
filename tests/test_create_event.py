import importlib.util
import io
import json
import sys
from pathlib import Path

import helpers
import pytest

# create_event/ has no __init__.py, so load the script by path. The guard
# around main() keeps this import free of side effects.
_RUN_PATH = Path(__file__).resolve().parent.parent / "create_event" / "run.py"
_spec = importlib.util.spec_from_file_location("create_event_run", _RUN_PATH)
assert _spec is not None and _spec.loader is not None
create_event = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(create_event)

ATHENS_VTIMEZONE_MARKER = b"TZID:Europe/Athens"


def make_parameters(**overrides: object) -> dict[str, object]:
    parameters: dict[str, object] = {
        "summary": "Dinner",
        "start": "2026-09-28T21:00:00",
        "end": "2026-09-28T22:00:00",
    }
    parameters.update(overrides)
    return parameters


def use_default_timezone(monkeypatch: pytest.MonkeyPatch, timezone: str) -> None:
    monkeypatch.setattr(helpers, "load_config", lambda: {"default_timezone": timezone})


# --- acceptance: zoned datetimes --------------------------------------------


def test_bare_datetime_uses_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_default_timezone(monkeypatch, "Europe/Athens")
    calendar, uid = create_event.build_calendar(make_parameters())

    serialized = calendar.to_ical()
    assert b"DTSTART;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"DTEND;TZID=Europe/Athens:20260928T220000" in serialized
    assert b"BEGIN:VTIMEZONE" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized
    assert uid in serialized.decode("utf-8")


def test_offset_datetime_matches_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 21:00+03:00 is the same instant as 21:00 Europe/Athens in September.
    use_default_timezone(monkeypatch, "Europe/Athens")
    calendar, _ = create_event.build_calendar(
        make_parameters(
            start="2026-09-28T21:00:00+03:00",
            end="2026-09-28T22:00:00+03:00",
        )
    )

    serialized = calendar.to_ical()
    assert b"DTSTART;TZID=Europe/Athens:20260928T210000" in serialized
    assert b"DTEND;TZID=Europe/Athens:20260928T220000" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized


def test_explicit_timezone_overrides_config_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_default_timezone(monkeypatch, "UTC")
    calendar, _ = create_event.build_calendar(
        make_parameters(timezone="Europe/Athens")
    )

    serialized = calendar.to_ical()
    assert b"DTSTART;TZID=Europe/Athens:20260928T210000" in serialized
    assert ATHENS_VTIMEZONE_MARKER in serialized


# --- all-day events ----------------------------------------------------------


def test_date_only_creates_all_day_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_default_timezone(monkeypatch, "Europe/Athens")
    calendar, _ = create_event.build_calendar(
        make_parameters(start="2026-09-28", end="2026-09-29")
    )

    serialized = calendar.to_ical()
    assert b"DTSTART;VALUE=DATE:20260928" in serialized
    assert b"DTEND;VALUE=DATE:20260929" in serialized
    assert b"BEGIN:VTIMEZONE" not in serialized


@pytest.mark.parametrize(
    "start, end",
    [
        ("2026-09-28", "2026-09-28T22:00:00"),
        ("2026-09-28T21:00:00", "2026-09-29"),
    ],
)
def test_mixed_date_and_datetime_exits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    start: str,
    end: str,
) -> None:
    use_default_timezone(monkeypatch, "Europe/Athens")

    with pytest.raises(SystemExit) as excinfo:
        create_event.build_calendar(make_parameters(start=start, end=end))

    assert excinfo.value.code == 1
    assert "start and end must both be dates or both be datetimes" in (
        capsys.readouterr().err
    )


# --- main wiring -------------------------------------------------------------


class FakeCalendar:
    def __init__(self) -> None:
        self.payload: str | None = None

    def save_event(self, payload: str) -> None:
        self.payload = payload


def test_main_accepts_timezone_and_serializes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_calendar = FakeCalendar()
    use_default_timezone(monkeypatch, "UTC")
    monkeypatch.setattr(helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        helpers, "find_calendar_by_name", lambda principal, name: fake_calendar
    )

    payload = {
        "calendar_name": "Personal",
        "summary": "Dinner",
        "start": "2026-09-28T21:00:00",
        "end": "2026-09-28T22:00:00",
        "timezone": "Europe/Athens",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    create_event.main()

    assert fake_calendar.payload is not None
    assert "DTSTART;TZID=Europe/Athens:20260928T210000" in fake_calendar.payload
    result = json.loads(capsys.readouterr().out)
    assert result["summary"] == "Dinner"
    assert result["uid"]
