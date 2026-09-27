#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata"]
# ///

import json
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "..")
import helpers
import icalendar

TIME_PARAMETERS = ("due", "timezone")

ALLOWED_STATUSES = ("NEEDS-ACTION", "IN-PROCESS", "COMPLETED", "CANCELLED")


def _update_status(component: icalendar.cal.Component, status: str) -> None:
    if status not in ALLOWED_STATUSES:
        print(
            f"Invalid status: {status} (allowed: {', '.join(ALLOWED_STATUSES)})",
            file=sys.stderr,
        )
        sys.exit(1)

    component["STATUS"] = icalendar.vText(status)
    if status == "COMPLETED":
        # Stamp the completion time in UTC only if the client did not already.
        if component.get("COMPLETED") is None:
            component["COMPLETED"] = icalendar.vDDDTypes(datetime.now(timezone.utc))
        return

    component.pop("COMPLETED", None)
    percent = component.get("PERCENT-COMPLETE")
    if percent is not None and int(percent) == 100:
        component.pop("PERCENT-COMPLETE", None)


def _update_times(
    component: icalendar.cal.Component,
    parameters: dict[str, object],
    default_zone: helpers.DefaultZone,
) -> None:
    due_given = "due" in parameters
    due_value = parameters.get("due")
    timezone_given = "timezone" in parameters
    due_removed = due_given and due_value is None

    # DTSTART is only re-expressed when a new due or an explicit zone is given;
    # removing DUE on its own must leave DTSTART's value alone.
    rewrite_start = timezone_given or (due_given and due_value is not None)

    # The target zone is not needed when DUE is merely removed: avoid touching
    # the config default in that case.
    target: ZoneInfo | None = None
    if timezone_given or (due_given and due_value is not None):
        target = helpers.resolve_target_zone(component, parameters, default_zone, "DUE")

    existing_due = helpers.read_property(component, "DUE")
    final_due: date | datetime | None = None
    if due_value is not None:
        assert target is not None
        final_due = helpers.parse_datetime(str(due_value), target)
    elif existing_due is not None and not due_removed:
        assert target is not None
        final_due = helpers.reinterpret_time(existing_due, target)

    existing_start = helpers.read_property(component, "DTSTART")
    final_start: date | datetime | None = None
    if existing_start is not None and rewrite_start:
        assert target is not None
        final_start = helpers.reinterpret_time(existing_start, target)

    if (
        final_due is not None
        and final_start is not None
        and isinstance(final_due, datetime) != isinstance(final_start, datetime)
    ):
        print("Cannot mix all-day and timed due/start", file=sys.stderr)
        sys.exit(1)

    # Assigning a fresh property replaces the old one, so a stale TZID param
    # cannot linger. vDDDTypes renders TZID from the datetime's tzinfo.
    if due_removed:
        component.pop("DUE", None)
    elif final_due is not None:
        component["DUE"] = icalendar.vDDDTypes(final_due)
        # RFC 5545 forbids DUE and DURATION on the same VTODO.
        component.pop("DURATION", None)

    if final_start is not None:
        component["DTSTART"] = icalendar.vDDDTypes(final_start)


def _update_priority(component: icalendar.cal.Component, priority: object) -> None:
    if not isinstance(priority, int) or not 0 <= priority <= 9:
        print(
            f"Invalid priority: {priority} (must be an integer 0-9)",
            file=sys.stderr,
        )
        sys.exit(1)
    component["PRIORITY"] = icalendar.vInt(priority)


def apply_update(
    calendar: icalendar.Calendar,
    parameters: dict[str, object],
    default_zone: helpers.DefaultZone,
) -> icalendar.cal.Component:
    component = next(c for c in calendar.walk() if c.name == "VTODO")

    if "summary" in parameters:
        component["SUMMARY"] = icalendar.vText(parameters["summary"])
    if "description" in parameters:
        component["DESCRIPTION"] = icalendar.vText(parameters["description"])
    if "priority" in parameters:
        _update_priority(component, parameters["priority"])
    if "status" in parameters:
        _update_status(component, str(parameters["status"]))

    if any(name in parameters for name in TIME_PARAMETERS):
        _update_times(component, parameters, default_zone)
        # Keep existing VTIMEZONE blocks and add any the target zone needs.
        calendar.add_missing_timezones()

    return component


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(
        parameters,
        {
            "calendar_name",
            "uid",
            "summary",
            "description",
            "priority",
            "due",
            "timezone",
            "status",
        },
    )
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    todo = calendar.todo_by_uid(uid)

    parsed = icalendar.Calendar.from_ical(todo.data)
    # Pass the resolver itself: the configured default is only needed when no
    # explicit timezone is given and the stored DUE has no valid IANA TZID.
    component = apply_update(parsed, parameters, helpers.resolve_timezone)

    todo.data = parsed.to_ical().decode("utf-8")
    todo.save()

    print(json.dumps({
        "uid": uid,
        "summary": str(component.get("SUMMARY", "")),
    }))


if __name__ == "__main__":
    main()
