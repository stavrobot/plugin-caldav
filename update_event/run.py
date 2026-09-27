#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys
from datetime import date, datetime

sys.path.insert(0, "..")
import helpers
import icalendar

TIME_PARAMETERS = ("start", "end", "timezone")


def _update_times(
    component: icalendar.cal.Component,
    parameters: dict[str, object],
    default_zone: helpers.DefaultZone,
) -> None:
    target = helpers.resolve_target_zone(component, parameters, default_zone)

    existing_start = helpers.read_property(component, "DTSTART")
    if "start" in parameters:
        final_start: date | datetime | None = helpers.parse_datetime(
            str(parameters["start"]), target
        )
    elif existing_start is not None:
        final_start = helpers.reinterpret_time(existing_start, target)
    else:
        final_start = None

    existing_end = helpers.read_property(component, "DTEND")
    if "end" in parameters:
        final_end: date | datetime | None = helpers.parse_datetime(
            str(parameters["end"]), target
        )
    elif existing_end is not None:
        final_end = helpers.reinterpret_time(existing_end, target)
    else:
        # DURATION-based event: leave the end (and thus the duration) alone.
        final_end = None

    if (
        final_start is not None
        and final_end is not None
        and isinstance(final_start, datetime) != isinstance(final_end, datetime)
    ):
        print("Cannot mix all-day and timed start/end", file=sys.stderr)
        sys.exit(1)

    # Assigning a fresh property replaces the old one, so a stale TZID param
    # cannot linger. vDDDTypes renders TZID from the datetime's tzinfo.
    if final_start is not None:
        component["DTSTART"] = icalendar.vDDDTypes(final_start)
    if final_end is not None:
        component["DTEND"] = icalendar.vDDDTypes(final_end)
        # RFC 5545 forbids DTEND and DURATION on the same event.
        component.pop("DURATION", None)


def apply_update(
    calendar: icalendar.Calendar,
    parameters: dict[str, object],
    default_zone: helpers.DefaultZone,
) -> icalendar.cal.Component:
    component = next(c for c in calendar.walk() if c.name == "VEVENT")

    if "summary" in parameters:
        component["SUMMARY"] = icalendar.vText(parameters["summary"])
    if "description" in parameters:
        component["DESCRIPTION"] = icalendar.vText(parameters["description"])
    if "location" in parameters:
        component["LOCATION"] = icalendar.vText(parameters["location"])

    if any(name in parameters for name in TIME_PARAMETERS):
        _update_times(component, parameters, default_zone)
        # Keep existing VTIMEZONE blocks and add any the target zone needs.
        calendar.add_missing_timezones()

    return component


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "uid", "summary", "description", "location", "start", "end", "timezone"})
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    event = calendar.event_by_uid(uid)

    parsed = icalendar.Calendar.from_ical(event.data)
    # Pass the resolver itself: the configured default is only needed when no
    # explicit timezone is given and the stored DTSTART has no valid IANA TZID.
    component = apply_update(parsed, parameters, helpers.resolve_timezone)

    event.data = parsed.to_ical().decode("utf-8")
    event.save()

    print(json.dumps({
        "uid": uid,
        "summary": str(component.get("SUMMARY", "")),
    }))


if __name__ == "__main__":
    main()
