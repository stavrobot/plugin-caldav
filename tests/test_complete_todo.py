import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# complete_todo/run.py is a standalone script, not a package module, and its
# main() only runs under __main__, so load it by path.
_SPEC = importlib.util.spec_from_file_location(
    "complete_todo_run", ROOT / "complete_todo" / "run.py"
)
assert _SPEC is not None and _SPEC.loader is not None
complete_todo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(complete_todo)


class FakeTodo:
    def __init__(self, status: str | None) -> None:
        self.icalendar_component = {} if status is None else {"STATUS": status}
        self.complete_calls = 0

    def is_pending(self) -> bool:
        # Mirrors caldav: NEEDS-ACTION/IN-PROCESS (and absent STATUS) are pending.
        return self.icalendar_component.get("STATUS", "NEEDS-ACTION") in (
            "NEEDS-ACTION",
            "IN-PROCESS",
        )

    def complete(self) -> None:
        self.complete_calls += 1


class FakeCalendar:
    def __init__(self, todo: FakeTodo) -> None:
        self._todo = todo

    def todo_by_uid(self, uid: str) -> FakeTodo:
        return self._todo


def patch_main(monkeypatch: pytest.MonkeyPatch, todo: FakeTodo) -> None:
    monkeypatch.setattr(complete_todo.helpers, "get_principal", lambda: object())
    monkeypatch.setattr(
        complete_todo.helpers,
        "find_calendar_by_name",
        lambda principal, name: FakeCalendar(todo),
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"calendar_name": "Personal", "uid": "abc"})),
    )


def run_main(
    monkeypatch: pytest.MonkeyPatch, todo: FakeTodo, capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    patch_main(monkeypatch, todo)

    complete_todo.main()

    return json.loads(capsys.readouterr().out)


# --- the pure check, exercised through a fake todo --------------------------


def test_pending_todo_is_completed() -> None:
    todo = FakeTodo("NEEDS-ACTION")

    assert complete_todo.complete_if_pending(todo, "abc") is False
    assert todo.complete_calls == 1


def test_todo_without_status_is_completed() -> None:
    todo = FakeTodo(None)

    assert complete_todo.complete_if_pending(todo, "abc") is False
    assert todo.complete_calls == 1


def test_already_completed_todo_is_left_untouched() -> None:
    todo = FakeTodo("COMPLETED")

    assert complete_todo.complete_if_pending(todo, "abc") is True
    assert todo.complete_calls == 0


def test_cancelled_todo_exits(capsys: pytest.CaptureFixture[str]) -> None:
    todo = FakeTodo("CANCELLED")

    with pytest.raises(SystemExit) as excinfo:
        complete_todo.complete_if_pending(todo, "abc")

    assert excinfo.value.code == 1
    assert "Todo is cancelled: abc" in capsys.readouterr().err
    assert todo.complete_calls == 0


# --- the JSON contract crossing the main() boundary -------------------------


def test_main_reports_already_completed_without_saving(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    todo = FakeTodo("COMPLETED")

    assert run_main(monkeypatch, todo, capsys) == {
        "uid": "abc",
        "completed": True,
        "already_completed": True,
    }
    assert todo.complete_calls == 0


def test_main_completes_pending_todo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    todo = FakeTodo("NEEDS-ACTION")

    assert run_main(monkeypatch, todo, capsys) == {
        "uid": "abc",
        "completed": True,
        "already_completed": False,
    }
    assert todo.complete_calls == 1


def test_main_exits_on_cancelled_todo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    todo = FakeTodo("CANCELLED")
    patch_main(monkeypatch, todo)

    with pytest.raises(SystemExit) as excinfo:
        complete_todo.main()

    assert excinfo.value.code == 1
    assert "Todo is cancelled: abc" in capsys.readouterr().err
    assert todo.complete_calls == 0
