#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar"]
# ///

import json
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "..")
import helpers
import icalendar


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "summary", "due", "description", "priority"})
    calendar_name: str = parameters["calendar_name"]
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
        vtodo.add("DUE", datetime.fromisoformat(due_string))
    if description:
        vtodo.add("DESCRIPTION", description)
    if priority is not None:
        vtodo.add("PRIORITY", priority)

    calendar_object.add_component(vtodo)

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    calendar.save_todo(calendar_object.to_ical().decode("utf-8"))

    print(json.dumps({"uid": todo_uid, "summary": summary}))


main()
