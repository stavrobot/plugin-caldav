#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers
import icalendar


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "uid"})
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    event = calendar.event_by_uid(uid)

    parsed = icalendar.Calendar.from_ical(event.data)
    component = next(
        c for c in parsed.walk() if c.name == "VEVENT"
    )

    raw_start = component.get("DTSTART")
    raw_end = component.get("DTEND")

    start_value = raw_start.dt if raw_start else None
    end_value = raw_end.dt if raw_end else None

    print(json.dumps({
        "data": event.data,
        "uid": str(component.get("UID", "")),
        "summary": str(component.get("SUMMARY", "")),
        "start": start_value.isoformat() if start_value is not None else None,
        "end": end_value.isoformat() if end_value is not None else None,
        "description": str(component.get("DESCRIPTION", "")),
        "location": str(component.get("LOCATION", "")),
        "status": str(component.get("STATUS", "")),
    }))


main()
