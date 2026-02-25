#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers
import icalendar


def extract_todo_fields(component: icalendar.cal.Component) -> dict[str, str | None]:
    raw_due = component.get("DUE")
    due_value = raw_due.dt if raw_due else None
    # date objects have no isoformat with time component, but both date and
    # datetime support .isoformat(), so this handles both uniformly.
    due_string = due_value.isoformat() if due_value is not None else None

    raw_priority = component.get("PRIORITY")
    priority_string = str(int(raw_priority)) if raw_priority is not None else ""

    return {
        "uid": str(component.get("UID", "")),
        "summary": str(component.get("SUMMARY", "")),
        "due": due_string,
        "status": str(component.get("STATUS", "")),
        "description": str(component.get("DESCRIPTION", "")),
        "priority": priority_string,
    }


def main() -> None:
    parameters = json.load(sys.stdin)
    calendar_name: str = parameters["calendar_name"]
    status_filter: str | None = parameters.get("status")

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)

    # include_completed=True ensures we retrieve todos in any status, not just
    # NEEDS-ACTION, so that optional status filtering works across all states.
    todos = calendar.todos(include_completed=True)

    result = []
    for todo in todos:
        parsed = icalendar.Calendar.from_ical(todo.data)
        for component in parsed.walk():
            if component.name == "VTODO":
                fields = extract_todo_fields(component)
                if status_filter is None or fields["status"] == status_filter:
                    result.append(fields)

    print(json.dumps(result))


main()
