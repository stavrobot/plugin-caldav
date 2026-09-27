---
id: rep-pvofu
status: closed
deps: []
links: []
created: 2026-09-27T12:08:40Z
type: bug
priority: 2
assignee: Stavros Korokithakis
---
# complete_todo: no-op for already-completed todos, document recurrence

ready for implementation

Objective: completing an already-completed todo no longer crashes with an AssertionError stack trace (caldav Todo.complete() asserts the todo is pending).

Scope: complete_todo/ (run.py, manifest.json), tests.
- If the todo's STATUS is already COMPLETED, do not modify or save it; output {"uid": ..., "completed": true, "already_completed": true}. Otherwise behave as today and output already_completed false.
- Manifest description: state that for a recurring todo (RRULE) this marks the whole series completed.
- Keep caldav's complete() for the normal path (it preserves DUE TZID; verified). Factor so the check is testable without CalDAV (fake todo object).

Non-goals: recurring-todo handling (handle_rrule) - considered and rejected for now because caldav computes the next occurrence in UTC, which drifts across DST.

