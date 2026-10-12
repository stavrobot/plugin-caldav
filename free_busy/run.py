#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav", "icalendar>=6.1", "tzdata", "recurring-ical-events"]
# ///

import json
import logging
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, "..")
import helpers
import icalendar
import recurring_ical_events
from icalendar.prop import vDDDTypes

MAX_RANGE = timedelta(days=31)
_CONTACT_BIRTHDAYS = "contact_birthdays"
_DEFAULT_EXCLUDED_CALENDARS = "Birthdays,Namedays"


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def _range_bound(value: str, zone: ZoneInfo, *, is_end: bool) -> datetime:
    parsed = helpers.parse_datetime(value, zone)
    if isinstance(parsed, datetime):
        return parsed.astimezone(timezone.utc)
    # A date-only end covers the whole day, i.e. the next local midnight.
    midnight = datetime(parsed.year, parsed.month, parsed.day, tzinfo=zone)
    if is_end:
        midnight += timedelta(days=1)
    return midnight.astimezone(timezone.utc)


def _excluded_calendar_names(config: dict[str, object]) -> set[str]:
    # Unset or null means the default; only an explicit string overrides it.
    raw = config.get("freebusy_excluded_calendars")
    value = _DEFAULT_EXCLUDED_CALENDARS if raw is None else str(raw)
    return {name.strip().lower() for name in value.split(",") if name.strip()}


def _is_contact_birthdays(url: object) -> bool:
    path = urlparse(str(url)).path
    return path.rstrip("/").rsplit("/", 1)[-1] == _CONTACT_BIRTHDAYS


def _supports_events(calendar: object) -> bool:
    components = calendar.get_supported_components()
    return any(str(component).upper() == "VEVENT" for component in components)


def _to_utc(value: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Floating or unresolvable TZID: keep the wall-clock time.
            return value.replace(tzinfo=zone).astimezone(timezone.utc)
        return value.astimezone(timezone.utc)
    # All-day DATE: local midnight.
    midnight = datetime(value.year, value.month, value.day, tzinfo=zone)
    return midnight.astimezone(timezone.utc)


def _occurrence_bounds(
    component: icalendar.cal.Component, zone: ZoneInfo
) -> tuple[datetime, datetime] | None:
    start = helpers.read_property(component, "DTSTART")
    if start is None:
        return None
    start_dt = _to_utc(start.value, zone)

    end = helpers.read_property(component, "DTEND")
    if end is not None:
        end_dt = _to_utc(end.value, zone)
    else:
        duration = component.get("DURATION")
        if duration is not None:
            end_dt = start_dt + duration.dt
        elif start.is_all_day:
            end_dt = start_dt + timedelta(days=1)
        else:
            # Timed event with no DTEND/DURATION: zero length, drop it.
            return None

    if end_dt <= start_dt:
        return None
    return start_dt, end_dt


def _is_busy(component: icalendar.cal.Component) -> bool:
    transp = component.get("TRANSP")
    if transp is not None and str(transp).strip().upper() == "TRANSPARENT":
        return False
    status = component.get("STATUS")
    cancelled = status is not None and str(status).strip().upper() == "CANCELLED"
    return not cancelled


def _resolve_legacy_offsets(calendar: icalendar.cal.Component) -> None:
    """Resolve legacy fixed-offset TZIDs before recurrence expansion.

    icalendar keeps a TZID like 'UTC+03:00' without a VTIMEZONE as a naive value
    carrying the TZID parameter, and recurring_ical_events then drops the TZID.
    helpers.read_property resolves such TZIDs to a fixed offset, so rewrite the
    time properties up front to keep the instant.
    """
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        for name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
            raw = component.get(name)
            value = getattr(raw, "dt", None)
            if (
                raw is None
                or not isinstance(value, datetime)
                or value.tzinfo is not None
            ):
                continue
            parsed = helpers.read_property(component, name)
            if parsed is None or parsed.value.tzinfo is None:
                continue
            component[name] = vDDDTypes(parsed.value)


def _collect_intervals(
    zone: ZoneInfo, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    config = helpers.load_config()
    excluded = _excluded_calendar_names(config)

    # All intervals are compared as UTC instants, because datetimes sharing one
    # ZoneInfo compare by wall time and would be wrong across a DST fall-back.
    # Nextcloud's server-side time filter reads floating/all-day values as UTC,
    # so pad the search window and expand recurrences/overrides locally.
    window_start = start - timedelta(days=1)
    window_end = end + timedelta(days=1)

    intervals: list[tuple[datetime, datetime]] = []
    principal = helpers.get_principal()
    for calendar in principal.calendars():
        if _is_contact_birthdays(calendar.url):
            continue
        if str(calendar.name).strip().lower() in excluded:
            continue
        if not _supports_events(calendar):
            continue

        events = calendar.search(start=window_start, end=window_end, event=True)
        for event in events:
            parsed = icalendar.Calendar.from_ical(event.data)
            _resolve_legacy_offsets(parsed)
            occurrences = recurring_ical_events.of(parsed).between(
                window_start, window_end
            )
            for occurrence in occurrences:
                if not _is_busy(occurrence):
                    continue
                bounds = _occurrence_bounds(occurrence, zone)
                if bounds is None:
                    continue
                intervals.append(bounds)
    return intervals


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    clipped = []
    for interval_start, interval_end in intervals:
        clipped_start = max(interval_start, start)
        clipped_end = min(interval_end, end)
        if clipped_end > clipped_start:
            clipped.append((clipped_start, clipped_end))

    clipped.sort()
    merged: list[tuple[datetime, datetime]] = []
    for interval_start, interval_end in clipped:
        if merged and interval_start <= merged[-1][1]:
            if interval_end > merged[-1][1]:
                merged[-1] = (merged[-1][0], interval_end)
        else:
            merged.append((interval_start, interval_end))
    return merged


def main() -> None:
    # caldav and icalendar can write response bodies and event data to stderr.
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")

    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"start", "end"})

    zone = helpers.resolve_timezone()
    start = _range_bound(parameters["start"], zone, is_end=False)
    end = _range_bound(parameters["end"], zone, is_end=True)
    if end <= start:
        _fail("The end of the range must be after the start.")
    # The cap measures the requested wall-clock span in the default zone, so a
    # fall-back day (25 hours) does not push a calendar-month request over it.
    wall_start = start.astimezone(zone).replace(tzinfo=None)
    wall_end = end.astimezone(zone).replace(tzinfo=None)
    if wall_end - wall_start > MAX_RANGE:
        _fail("The range must not exceed 31 days.")

    try:
        intervals = _collect_intervals(zone, start, end)
    except Exception as exception:  # noqa: BLE001
        # Never echo the exception message: caldav includes response bodies.
        _fail(f"Failed to read calendars ({type(exception).__name__})")

    busy = [
        {
            "start": interval_start.astimezone(zone).isoformat(),
            "end": interval_end.astimezone(zone).isoformat(),
        }
        for interval_start, interval_end in _merge_intervals(intervals, start, end)
    ]
    print(json.dumps({"busy": busy}))


if __name__ == "__main__":
    main()
