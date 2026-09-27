#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "..")
import helpers
import icalendar


def build_calendar(parameters: dict[str, object]) -> tuple[icalendar.Calendar, str]:
    """Build the VCALENDAR for an event without touching CalDAV.

    Bare datetimes are interpreted in the resolved timezone, offset datetimes
    are converted to it, and date-only values produce an all-day event.
    """
    summary: str = parameters["summary"]
    start_string: str = parameters["start"]
    end_string: str = parameters["end"]
    description: str = parameters.get("description", "")
    location: str = parameters.get("location", "")

    zone = helpers.resolve_timezone(parameters.get("timezone"))
    start_value = helpers.parse_datetime(start_string, zone)
    end_value = helpers.parse_datetime(end_string, zone)

    start_is_all_day = not isinstance(start_value, datetime)
    end_is_all_day = not isinstance(end_value, datetime)
    if start_is_all_day != end_is_all_day:
        print(
            "start and end must both be dates or both be datetimes",
            file=sys.stderr,
        )
        sys.exit(1)

    event_uid = str(uuid.uuid4())

    calendar_object = icalendar.Calendar()
    # Required per RFC 5545 to identify the product creating the data.
    calendar_object.add("PRODID", "-//caldav-plugin//EN")
    calendar_object.add("VERSION", "2.0")

    vevent = icalendar.Event()
    vevent.add("UID", event_uid)
    vevent.add("SUMMARY", summary)
    vevent.add("DTSTART", start_value)
    vevent.add("DTEND", end_value)
    if description:
        vevent.add("DESCRIPTION", description)
    if location:
        vevent.add("LOCATION", location)

    calendar_object.add_component(vevent)
    # Date-only events need no zone; zoned datetimes need a matching VTIMEZONE.
    calendar_object.add_missing_timezones()

    return calendar_object, event_uid


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(
        parameters,
        {"calendar_name", "summary", "start", "end", "description", "location", "timezone"},
    )
    calendar_name: str = parameters["calendar_name"]

    calendar_object, event_uid = build_calendar(parameters)

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    calendar.save_event(calendar_object.to_ical().decode("utf-8"))

    print(json.dumps({"uid": event_uid, "summary": parameters["summary"]}))


if __name__ == "__main__":
    main()
