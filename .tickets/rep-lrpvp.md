---
id: rep-lrpvp
status: closed
deps: [rep-wofgy]
links: []
created: 2026-09-27T12:08:40Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# New update_todo tool

ready for implementation

Objective: add an update_todo tool, mirroring update_event (read update_event/run.py first).

Scope: new update_todo/ (run.py, manifest.json), helpers.py, update_event/run.py (refactor only), README tool table, tests.
- Parameters: calendar_name, uid (required); optional summary, description, priority (int 0-9), due, timezone, status. Only given fields change. Reject unknown parameters via helpers.validate_parameters.
- Zone rule same as update_event: 'timezone' param > existing DUE TZID if valid IANA > config default_timezone (resolved lazily, only when it is the fallback). If due or timezone is given, rewrite DUE and, if present, DTSTART in the target zone: new due value parsed with helpers.parse_datetime; unchanged values re-expressed (aware keep instant, floating keep wall clock, all-day untouched). Mixed all-day/timed DTSTART vs DUE -> error, exit 1. Call add_missing_timezones(); keep existing VTIMEZONEs.
- 'due': null removes DUE (and does not touch DTSTART's value unless timezone is given).
- Setting due removes DURATION (RFC 5545 forbids DUE with DURATION).
- status: allowed values NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED; others -> error. NEEDS-ACTION/IN-PROCESS/CANCELLED remove COMPLETED (and PERCENT-COMPLETE if 100). COMPLETED sets COMPLETED to now in UTC if absent.
- Move update_event's target-zone selection and value re-expression into helpers.py so both tools share it; keep update_event behaviour and tests unchanged.
- Output: {uid, summary}. Script deps: ["caldav", "icalendar>=6.1", "tzdata"].

Non-goals: recurrence (RRULE) handling; editing VTODOs beyond the first; moving todos between calendars.

