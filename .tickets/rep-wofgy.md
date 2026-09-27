---
id: rep-wofgy
status: closed
deps: [rep-uwdkf]
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# create_todo/list_todos: timezone handling for due dates

ready for implementation

Objective: todos get the same timezone handling events got (see rep-uwdkf, rep-bonlf, rep-phtot and helpers.py).

Scope: create_todo/, list_todos/ (run.py + manifest.json), tests.
- create_todo: optional 'timezone' parameter (IANA) overriding config default_timezone. Parse 'due' with helpers.parse_datetime: bare -> in zone, offset -> converted, YYYY-MM-DD -> all-day VALUE=DATE. Write TZID=<IANA> and call add_missing_timezones() before saving. Factor calendar building into a testable function; guard main() with `if __name__ == "__main__"`, like create_event.
- list_todos: 'due' via helpers.format_property (offset for zoned/UTC/legacy, bare for floating, date for all-day) plus a 'timezone' field with the same labels as events. Mention the formats in the manifest description (no invented manifest keys).
- Script deps: ["caldav", "icalendar>=6.1", "tzdata"].

Non-goals: returning DTSTART from list_todos; changes to complete_todo or recurrence.

