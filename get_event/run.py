#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
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

    print(json.dumps({
        "data": event.data,
        **helpers.extract_event_fields(component),
        "location": str(component.get("LOCATION", "")),
        "status": str(component.get("STATUS", "")),
    }))


if __name__ == "__main__":
    main()
