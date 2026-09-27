---
id: rep-uwdkf
status: closed
deps: []
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# Shared timezone helpers, default_timezone config, pytest setup

ready for implementation

Objective: add the shared datetime/timezone logic that create_event, update_event, list_events and get_event will use. Background: events are written as floating times or with a nonstandard TZID="UTC+03:00" and no VTIMEZONE, so clients show them at the wrong time.

Scope:
- helpers.py: pure functions (no CalDAV calls), roughly:
  - load config (split out of get_principal so both use it) and resolve the zone: optional 'timezone' parameter > config 'default_timezone' > UTC. Invalid IANA name -> print clear error to stderr, exit 1 (same style as existing helpers).
  - parse an input string in a zone: 'YYYY-MM-DD' -> date (all-day); bare datetime -> localized in zone; datetime with offset -> converted to zone (same instant).
  - read a DTSTART/DTEND property as an aware datetime / date / naive, honouring the TZID parameter: IANA name -> ZoneInfo; 'UTC+HH:MM'/'UTC-HH:MM' -> fixed offset; unknown TZID with no VTIMEZONE -> naive value, keep raw TZID. Note: icalendar parses TZID="UTC+03:00" as a naive datetime and leaves TZID only as a param.
  - format a DTSTART/DTEND for output -> (iso string, timezone label). Labels: IANA TZID, 'UTC', legacy TZID as stored (e.g. 'UTC+03:00'), 'floating' (bare time, no offset), None for all-day dates, raw TZID for unknown zones.
- manifest.json: add optional config 'default_timezone' (IANA name, e.g. Europe/Athens; UTC if unset). README: document it.
- tests/: pytest, fed with iCal text fixtures (zoned with VTIMEZONE, floating, UTC Z, legacy TZID="UTC+03:00", all-day). Run with: uv run --with pytest --with caldav --with icalendar --with tzdata pytest. Document the command in README briefly.
- Script dependency lists in tools that use these helpers should become ["caldav", "icalendar>=6.1", "tzdata"] (done in the per-tool tickets).

Non-goals: do not change the tool run.py files here (other tickets). No live CalDAV access in tests, ever. No todo changes.

## Design

Keep everything in helpers.py (existing shared module); no new module. Calendar.add_missing_timezones() (icalendar>=6.1) generates VTIMEZONE from zoneinfo; verified working in 7.3.0. Floating values have no offset; do not render them in default_timezone, flag them instead.

