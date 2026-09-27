---
id: rep-phtot
status: closed
deps: [rep-uwdkf]
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# list_events/get_event: return offsets and timezone field

ready for implementation

Objective: callers can tell zoned, UTC, legacy fixed-offset, floating and all-day events apart.

Scope: list_events/run.py, get_event/run.py, their manifests, tests.
- start/end: ISO 8601 with offset for zoned/UTC/legacy values (e.g. 2026-09-28T20:00:00+03:00); bare time for floating; YYYY-MM-DD for all-day.
- New 'timezone' field per event using the shared formatter labels: IANA TZID, 'UTC', legacy TZID as stored (e.g. 'UTC+03:00'), 'floating', null for all-day, raw TZID when unknown. One field covers both start and end (take it from DTSTART).
- list_events range filter: bare start/end range values are read in config default_timezone (UTC if unset) instead of naive.
- Manifests: describe the output fields.
- Script deps: ["caldav", "icalendar>=6.1", "tzdata"].
- Remove the duplicated extraction code between the two tools if the shared formatter makes it trivial.

Non-goals: changing other output fields; todos.

## Acceptance Criteria

- Tests (iCal fixtures only) show offsets and timezone field for zoned, floating, UTC and legacy TZID="UTC+03:00" events.

