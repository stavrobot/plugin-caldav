#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys
import uuid

sys.path.insert(0, "..")
import helpers
import icalendar


def build_calendar(parameters: dict[str, object]) -> tuple[icalendar.Calendar, str]:
    """Build the VCALENDAR for a todo without touching CalDAV.

    A bare due datetime is interpreted in the resolved timezone, an offset
    datetime is converted to it, and a date-only value produces an all-day due.
    """
    summary: str = parameters["summary"]
    due_string: str | None = parameters.get("due")
    description: str = parameters.get("description", "")
    priority: int | None = parameters.get("priority")

    todo_uid = str(uuid.uuid4())

    calendar_object = icalendar.Calendar()
    # Required per RFC 5545 to identify the product creating the data.
    calendar_object.add("PRODID", "-//caldav-plugin//EN")
    calendar_object.add("VERSION", "2.0")

    vtodo = icalendar.Todo()
    vtodo.add("UID", todo_uid)
    vtodo.add("SUMMARY", summary)
    if due_string is not None:
        # Only a due value needs a zone, so an absent due never touches config.
        zone = helpers.resolve_timezone(parameters.get("timezone"))
        vtodo.add("DUE", helpers.parse_datetime(due_string, zone))
    if description:
        vtodo.add("DESCRIPTION", description)
    if priority is not None:
        vtodo.add("PRIORITY", priority)

    calendar_object.add_component(vtodo)
    # Date-only due values need no zone; zoned datetimes need a matching VTIMEZONE.
    calendar_object.add_missing_timezones()

    return calendar_object, todo_uid


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(
        parameters,
        {"calendar_name", "summary", "due", "description", "priority", "timezone"},
    )
    calendar_name: str = parameters["calendar_name"]

    calendar_object, todo_uid = build_calendar(parameters)

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    calendar.save_todo(calendar_object.to_ical().decode("utf-8"))

    print(json.dumps({"uid": todo_uid, "summary": parameters["summary"]}))


if __name__ == "__main__":
    main()
