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
    helpers.validate_parameters(parameters, {"calendar_name", "start", "end"})
    calendar_name: str = parameters["calendar_name"]
    start_string: str | None = parameters.get("start")
    end_string: str | None = parameters.get("end")

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)

    if start_string is not None and end_string is not None:
        # Bare range values are read in the configured default timezone.
        zone = helpers.resolve_timezone()
        events = calendar.date_search(
            helpers.parse_datetime(start_string, zone),
            helpers.parse_datetime(end_string, zone),
        )
    else:
        events = calendar.events()

    result = []
    for event in events:
        parsed = icalendar.Calendar.from_ical(event.data)
        for component in parsed.walk():
            if component.name == "VEVENT":
                result.append(helpers.extract_event_fields(component))

    print(json.dumps(result))


if __name__ == "__main__":
    main()
