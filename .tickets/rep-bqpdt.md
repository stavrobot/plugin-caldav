---
id: rep-bqpdt
status: closed
deps: [rep-uwdkf]
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# update_event: preserve/switch TZID, keep VTIMEZONE

ready for implementation

Objective: updating times never drops or corrupts an event's zone.

Scope: update_event/run.py, update_event/manifest.json, tests.
- New optional parameter 'timezone' (IANA name).
- Rule: if any of start, end, timezone is given, rewrite BOTH DTSTART and DTEND (DTEND only if it exists or end is given; leave DURATION-based events alone otherwise) in the target zone.
  - Target zone: 'timezone' param if given; else existing DTSTART TZID if it is a valid IANA name; else config default_timezone (UTC if unset).
  - New value given: parse like create_event (bare -> in zone, offset -> converted, date-only -> VALUE=DATE).
  - Existing value not given: re-express in target zone. Zoned and legacy fixed-offset (TZID="UTC+03:00") values keep the same instant; floating values keep their clock time. Existing all-day values stay untouched.
  - Mixed date/datetime between final start and end -> error, exit 1.
- Keep existing VTIMEZONE blocks; call add_missing_timezones() before saving.
- Replace the current icalendar.vDatetime(...) assignment, which loses TZID.
- Script deps: ["caldav", "icalendar>=6.1", "tzdata"].

Non-goals: rewriting RRULE/EXDATE/RECURRENCE-ID; editing VEVENTs beyond the first (existing behaviour); removing unused VTIMEZONEs.

## Design

Effect worth keeping: update_event(timezone=Europe/Athens) on a floating 21:00 event makes it 21:00 Athens. This is how the owner fixes events already created wrongly.

## Acceptance Criteria

- Updating only start of an event stored with TZID=Europe/London (plus VTIMEZONE) keeps TZID=Europe/London and the VTIMEZONE.
- Tests use iCal fixtures only; factor the modify-calendar part so it is testable without CalDAV.

