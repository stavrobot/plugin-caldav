---
id: rep-byxmr
status: closed
deps: []
links: []
created: 2026-10-12T18:30:42Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# Add free_busy tool (busy blocks only, all calendars)

ready for implementation

Objective: new tool free_busy(start, end) returning only {"busy": [{"start", "end"}]} across every VEVENT calendar. It will be granted alone to an agent that talks to third parties, so it must leak nothing about events.

Scope: new free_busy/manifest.json + free_busy/run.py (same layout as list_events), plugin manifest.json config entry, README (tool table + config), tests/test_free_busy.py. Script deps: caldav, icalendar>=6.1, tzdata, recurring-ical-events (declare explicitly).

Behaviour:
- start/end: ISO 8601 date or datetime, parsed with helpers.parse_datetime in helpers.resolve_timezone() (default_timezone). Date-only start = local midnight; date-only end covers that whole day (next local midnight). Error if end <= start or range > 31 days (hard cap, error not truncate).
- Calendars: principal.calendars(), keep those whose get_supported_components() includes VEVENT. Exclude names in config freebusy_excluded_calendars (comma-separated, trimmed, case-insensitive, default 'Birthdays,Namedays' when key absent; empty string = no name exclusions). Always exclude calendars whose URL last path segment is contact_birthdays.
- Fetch: calendar.search(start, end, event=True) with range padded by 1 day each side (Nextcloud's server-side time filter reads floating/all-day as UTC). Do NOT use the server free-busy REPORT.
- Expand locally with recurring_ical_events (RRULE/RDATE/EXDATE/overrides) over the padded window. Per occurrence: skip TRANSP:TRANSPARENT and STATUS:CANCELLED. TENTATIVE/CONFIRMED/none = busy. Declined invitations are not special-cased.
- Times: aware -> convert to default zone. Floating or unresolvable TZID -> wall time in default zone (helpers.read_property already handles legacy UTC+03:00 TZIDs). All-day dates -> local midnight in default zone. Timed event with no DTEND/DURATION = zero length (drop). All-day with no end = 1 day.
- Merge overlapping and adjacent intervals across all calendars, clip to [start, end), drop empty. Output isoformat with offset in default zone, sorted.

Must not leak:
- Output has only key busy; each item only start and end.
- Any exception after input validation (listing, fetch, parse, any single calendar) -> stderr 'Failed to read calendars (<ExceptionTypeName>)', exit 1. Never print exception messages (caldav includes response bodies). No partial results.
- Disable logging (logging.disable) and suppress warnings at startup so caldav/icalendar cannot write event/response data to stderr.
- Input validation errors may echo only user input.

Non-goals: no changes to existing tools, no caching, no per-calendar info, no server REPORT, no PARTSTAT handling.

## Acceptance Criteria

Tests with a fake principal/calendars (no network) whose events put the marker SECRET in SUMMARY, DESCRIPTION, LOCATION, ATTENDEE, ORGANIZER, UID and calendar name; assert SECRET is absent from stdout and stderr on success and error paths (including a calendar whose search raises an exception whose message contains SECRET). Cover: each item has exactly start/end keys; RRULE with EXDATE and an overridden instance (moved, and one overridden to CANCELLED); TRANSPARENT and CANCELLED skipped; all-day event in Europe/Athens is busy 00:00+03:00 to next 00:00+03:00 (no 3h shift); floating event read in default zone; merge across calendars incl. adjacent; clipping to range; excluded calendars by name (case-insensitive) and contact_birthdays URL; non-VEVENT calendar ignored; 31-day cap; date-only end; end <= start rejected; one failing calendar fails the whole call. Existing tests still pass.

