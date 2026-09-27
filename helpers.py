import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import caldav
import icalendar

DEFAULT_TIMEZONE = "UTC"

_DATE_ONLY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
# Legacy clients store fixed offsets as TZID="UTC+03:00" with no VTIMEZONE.
_LEGACY_OFFSET_PATTERN = re.compile(r"UTC([+-])(\d{2}):(\d{2})")


@dataclass(frozen=True)
class IcalTime:
    # value is a date for all-day values, otherwise an aware datetime when the
    # zone could be resolved or a naive datetime when it could not.
    value: date | datetime
    # tzid is the raw TZID parameter exactly as stored (str), or None.
    tzid: str | None = None

    @property
    def is_all_day(self) -> bool:
        return not isinstance(self.value, datetime)

    @property
    def is_floating(self) -> bool:
        # Floating values have neither an offset nor a TZID.
        return (
            isinstance(self.value, datetime)
            and self.value.tzinfo is None
            and self.tzid is None
        )


def validate_parameters(parameters: dict[str, object], valid_names: set[str]) -> None:
    unknown = set(parameters.keys()) - valid_names
    if unknown:
        print(f"Unknown parameters: {', '.join(sorted(unknown))}", file=sys.stderr)
        sys.exit(1)


def load_config() -> dict[str, object]:
    # Tools run from their own subdirectory, so ../config.json resolves to
    # the plugin root's config.json regardless of where helpers.py lives.
    with open("../config.json") as config_file:
        return json.load(config_file)


def resolve_timezone(timezone_name: str | None = None) -> ZoneInfo:
    # Precedence: explicit parameter, then config default_timezone, then UTC.
    if timezone_name is None:
        configured = load_config().get("default_timezone")
        timezone_name = str(configured) if configured else DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"Invalid timezone: {timezone_name}", file=sys.stderr)
        sys.exit(1)


def parse_datetime(value: str, zone: ZoneInfo) -> date | datetime:
    value = value.strip()
    if _DATE_ONLY_PATTERN.fullmatch(value):
        return date.fromisoformat(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # Bare datetime: interpret the wall clock time in the target zone.
        localized = parsed.replace(tzinfo=zone)
        # A wall time inside a DST spring-forward gap does not exist. Python's
        # fold=0 silently shifts it, so round-trip through UTC and compare the
        # wall clock to detect it. Ambiguous fall-back times round-trip cleanly.
        roundtrip = localized.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) != parsed:
            print(
                f"Invalid local time {value}: does not exist in {zone.key} "
                "(DST transition)",
                file=sys.stderr,
            )
            sys.exit(1)
        return localized
    # Offset datetime: same instant, expressed in the target zone.
    return parsed.astimezone(zone)


def _legacy_offset(tzid: str) -> timezone | None:
    match = _LEGACY_OFFSET_PATTERN.fullmatch(tzid)
    if match is None:
        return None
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(-delta if sign == "-" else delta)


def read_property(component: icalendar.cal.Component, name: str) -> IcalTime | None:
    raw = component.get(name)
    if raw is None:
        return None

    raw_tzid = raw.params.get("TZID")
    tzid = str(raw_tzid) if raw_tzid is not None else None
    value = raw.dt

    if not isinstance(value, datetime):
        # DATE value (all-day); there is no timezone.
        return IcalTime(value=value, tzid=tzid)

    if value.tzinfo is not None:
        # icalendar already resolved this from an IANA TZID or a VTIMEZONE.
        return IcalTime(value=value, tzid=tzid)

    if tzid is None:
        # Floating time: no zone information at all.
        return IcalTime(value=value, tzid=None)

    offset = _legacy_offset(tzid)
    if offset is not None:
        return IcalTime(value=value.replace(tzinfo=offset), tzid=tzid)

    try:
        zone = ZoneInfo(tzid)
    except (ZoneInfoNotFoundError, ValueError):
        # Unknown TZID with no VTIMEZONE: keep the naive value and raw TZID.
        return IcalTime(value=value, tzid=tzid)
    return IcalTime(value=value.replace(tzinfo=zone), tzid=tzid)


def timezone_label(parsed: IcalTime) -> str | None:
    if parsed.is_all_day:
        return None
    # Any TZID (IANA, legacy fixed offset or unknown) is reported as stored.
    if parsed.tzid is not None:
        return parsed.tzid
    if parsed.value.tzinfo is None:
        return "floating"
    return "UTC"


def format_property(
    component: icalendar.cal.Component, name: str
) -> tuple[str | None, str | None]:
    parsed = read_property(component, name)
    if parsed is None:
        return None, None
    return parsed.value.isoformat(), timezone_label(parsed)


def extract_event_fields(component: icalendar.cal.Component) -> dict[str, str | None]:
    """Extract the event fields shared by list_events and get_event output.

    The single 'timezone' label is taken from DTSTART, since a VEVENT is not
    expected to mix zones between its start and end.
    """
    start, timezone = format_property(component, "DTSTART")
    end, _ = format_property(component, "DTEND")
    return {
        "uid": str(component.get("UID", "")),
        "summary": str(component.get("SUMMARY", "")),
        "start": start,
        "end": end,
        "timezone": timezone,
        "description": str(component.get("DESCRIPTION", "")),
    }


def get_principal() -> caldav.Principal:
    config = load_config()
    client = caldav.DAVClient(
        url=config["server_url"],
        username=config["username"],
        password=config["password"],
    )
    return client.principal()


def find_calendar_by_name(
    principal: caldav.Principal, name: str
) -> caldav.Calendar:
    calendars = principal.calendars()
    for calendar in calendars:
        if calendar.name == name:
            return calendar
    print(f"Calendar not found: {name}", file=sys.stderr)
    sys.exit(1)
