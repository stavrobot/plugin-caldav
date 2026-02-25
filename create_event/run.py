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
    helpers.validate_parameters(parameters, {"calendar_name", "summary", "start", "end", "description", "location"})
    calendar_name: str = parameters["calendar_name"]
    summary: str = parameters["summary"]
    start_string: str = parameters["start"]
    end_string: str = parameters["end"]
    description: str = parameters.get("description", "")
    location: str = parameters.get("location", "")

    start_datetime = datetime.fromisoformat(start_string)
    end_datetime = datetime.fromisoformat(end_string)

    event_uid = str(uuid.uuid4())

    calendar_object = icalendar.Calendar()
    # Required per RFC 5545 to identify the product creating the data.
    calendar_object.add("PRODID", "-//caldav-plugin//EN")
    calendar_object.add("VERSION", "2.0")

    vevent = icalendar.Event()
    vevent.add("UID", event_uid)
    vevent.add("SUMMARY", summary)
    vevent.add("DTSTART", start_datetime)
    vevent.add("DTEND", end_datetime)
    if description:
        vevent.add("DESCRIPTION", description)
    if location:
        vevent.add("LOCATION", location)

    calendar_object.add_component(vevent)

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    calendar.save_event(calendar_object.to_ical().decode("utf-8"))

    print(json.dumps({"uid": event_uid, "summary": summary}))


main()
