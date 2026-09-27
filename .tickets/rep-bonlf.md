---
id: rep-bonlf
status: closed
deps: [rep-uwdkf]
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# create_event: zoned DTSTART/DTEND with VTIMEZONE, timezone param

ready for implementation

Objective: create_event writes DTSTART/DTEND as TZID=<IANA> with a matching VTIMEZONE, or as VALUE=DATE for date-only input.

Scope: create_event/run.py, create_event/manifest.json, tests.
- New optional parameter 'timezone' (IANA name) overriding config default_timezone. Add to validate_parameters and manifest.
- Use the helpers from the shared ticket to parse start/end. Date-only start/end -> all-day (VALUE=DATE). Mixed date and datetime between start and end -> error to stderr, exit 1.
- Call calendar add_missing_timezones() before saving.
- Manifest: describe bare vs offset vs date-only handling; all-day end is exclusive (a one-day event on 2026-09-28 has end 2026-09-29), passed through unchanged.
- Script deps: ["caldav", "icalendar>=6.1", "tzdata"].

Non-goals: validating start < end; todos.

## Acceptance Criteria

- Bare 2026-09-28T21:00:00 with default_timezone=Europe/Athens -> DTSTART;TZID=Europe/Athens:20260928T210000 plus VTIMEZONE for Europe/Athens.
- 2026-09-28T21:00:00+03:00 gives the same result.
- Tests cover these without CalDAV access (factor the calendar-building part so it is testable).

