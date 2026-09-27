---
id: rep-wofgy
status: open
deps: [rep-uwdkf]
links: []
created: 2026-09-27T11:44:01Z
type: feature
priority: 2
assignee: Stavros Korokithakis
---
# Todos: timezone handling for due dates

Follow-up, NOT approved. create_todo parses 'due' with datetime.fromisoformat, so it has the same floating-time bug events had. list_todos output likely lacks zone info too. Apply the event helpers. Needs planning.

