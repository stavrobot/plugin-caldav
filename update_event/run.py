#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, "..")
import helpers
import icalendar

TIME_PARAMETERS = ("start", "end", "timezone")


# default_zone is either a resolved ZoneInfo or a callable that resolves the
# configured default lazily, so an invalid config value only matters when the
# fallback is actually needed.
DefaultZone = ZoneInfo | Callable[[], ZoneInfo]


def _resolve_target_zone(
    component: icalendar.cal.Component,
    parameters: dict[str, object],
    default_zone: DefaultZone,
) -> ZoneInfo:
    # Precedence: explicit timezone parameter, then the existing DTSTART TZID if
    # it names a real IANA zone, then the configured default.
    if "timezone" in parameters:
        return helpers.resolve_timezone(str(parameters["timezone"]))

    existing_start = helpers.read_property(component, "DTSTART")
    if existing_start is not None and existing_start.tzid is not None:
        try:
            return ZoneInfo(existing_start.tzid)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return default_zone() if callable(default_zone) else default_zone


def _reinterpret(existing: helpers.IcalTime, target: ZoneInfo) -> date | datetime:
    # All-day values carry no time to move.
    if existing.is_all_day:
        return existing.value
    value = existing.value
    if value.tzinfo is not None:
        # Zoned IANA or legacy fixed-offset values keep the same instant.
        return value.astimezone(target)
    # Floating (or an unresolvable TZID): keep the wall-clock time.
    return value.replace(tzinfo=target)


def _update_times(
    component: icalendar.cal.Component,
    parameters: dict[str, object],
    default_zone: DefaultZone,
) -> None:
    target = _resolve_target_zone(component, parameters, default_zone)

    existing_start = helpers.read_property(component, "DTSTART")
    if "start" in parameters:
        final_start: date | datetime | None = helpers.parse_datetime(
            str(parameters["start"]), target
        )
    elif existing_start is not None:
        final_start = _reinterpret(existing_start, target)
    else:
        final_start = None

    existing_end = helpers.read_property(component, "DTEND")
    if "end" in parameters:
        final_end: date | datetime | None = helpers.parse_datetime(
            str(parameters["end"]), target
        )
    elif existing_end is not None:
        final_end = _reinterpret(existing_end, target)
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
    default_zone: DefaultZone,
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
