#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers
import icalendar


def extract_todo_fields(component: icalendar.cal.Component) -> dict[str, str | None]:
    # format_property returns ISO 8601 with an offset for zoned/UTC/legacy
    # values, a bare local time for floating ones and YYYY-MM-DD for all-day.
    due, timezone = helpers.format_property(component, "DUE")

    raw_priority = component.get("PRIORITY")
    priority_string = str(int(raw_priority)) if raw_priority is not None else ""

    return {
        "uid": str(component.get("UID", "")),
        "summary": str(component.get("SUMMARY", "")),
        "due": due,
        "timezone": timezone,
        "status": str(component.get("STATUS", "")),
        "description": str(component.get("DESCRIPTION", "")),
        "priority": priority_string,
    }


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "status"})
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


if __name__ == "__main__":
    main()
