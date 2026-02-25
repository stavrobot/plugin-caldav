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


def extract_event_fields(component: icalendar.cal.Component) -> dict[str, str | None]:
    # icalendar vDDDTypes wrap both date and datetime; .dt gives the Python value.
    raw_start = component.get("DTSTART")
    raw_end = component.get("DTEND")

    start_value = raw_start.dt if raw_start else None
    end_value = raw_end.dt if raw_end else None

    # date objects have no isoformat with time component, but both date and
    # datetime support .isoformat(), so this handles both uniformly.
    start_string = start_value.isoformat() if start_value is not None else None
    end_string = end_value.isoformat() if end_value is not None else None

    return {
        "uid": str(component.get("UID", "")),
        "summary": str(component.get("SUMMARY", "")),
        "start": start_string,
        "end": end_string,
        "description": str(component.get("DESCRIPTION", "")),
    }


def main() -> None:
    parameters = json.load(sys.stdin)
    calendar_name: str = parameters["calendar_name"]
    start_string: str | None = parameters.get("start")
    end_string: str | None = parameters.get("end")

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)

    if start_string is not None and end_string is not None:
        start_datetime = datetime.fromisoformat(start_string)
        end_datetime = datetime.fromisoformat(end_string)
        events = calendar.date_search(start_datetime, end_datetime)
    else:
        events = calendar.events()

    result = []
    for event in events:
        parsed = icalendar.Calendar.from_ical(event.data)
        for component in parsed.walk():
            if component.name == "VEVENT":
                result.append(extract_event_fields(component))

    print(json.dumps(result))


main()
