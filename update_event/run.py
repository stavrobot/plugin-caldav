#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar"]
# ///

import json
import sys
from datetime import datetime

sys.path.insert(0, "..")
import helpers
import icalendar


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "uid", "summary", "description", "location", "start", "end"})
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    event = calendar.event_by_uid(uid)

    parsed = icalendar.Calendar.from_ical(event.data)
    component = next(
        c for c in parsed.walk() if c.name == "VEVENT"
    )

    if "summary" in parameters:
        component["SUMMARY"] = icalendar.vText(parameters["summary"])
    if "description" in parameters:
        component["DESCRIPTION"] = icalendar.vText(parameters["description"])
    if "location" in parameters:
        component["LOCATION"] = icalendar.vText(parameters["location"])
    if "start" in parameters:
        component["DTSTART"] = icalendar.vDatetime(
            datetime.fromisoformat(parameters["start"])
        )
    if "end" in parameters:
        component["DTEND"] = icalendar.vDatetime(
            datetime.fromisoformat(parameters["end"])
        )

    event.data = parsed.to_ical().decode("utf-8")
    event.save()

    print(json.dumps({
        "uid": uid,
        "summary": str(component.get("SUMMARY", "")),
    }))


main()
