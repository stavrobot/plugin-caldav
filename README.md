# CalDAV plugin for Stavrobot

Manage calendars, events, and todos on any CalDAV server.

## Installation

Ask Stavrobot:

> Install the plugin at https://github.com/stavrobot/plugin-caldav.git

Then configure it with your CalDAV server credentials:

- **server_url**: Your CalDAV server base URL (e.g. `https://caldav.example.com`)
- **username**: Username for authentication
- **password**: Password for authentication
- **default_timezone** (optional): IANA timezone name (e.g. `Europe/Athens`) used
  for datetimes passed without an offset. Defaults to `UTC`.

## Timezones

Event times are stored with an explicit timezone whenever possible:

- A datetime with an offset (`2026-09-28T21:00:00+03:00`) is converted to the
  target zone, preserving the instant.
- A bare datetime (`2026-09-28T21:00:00`) is interpreted as wall-clock time in
  the target zone: the tool's `timezone` parameter if given, otherwise
  `default_timezone`, otherwise `UTC`.
- A date-only value (`2026-09-28`) is an all-day event.

Events read back are reported with an ISO 8601 offset (zoned, UTC, or legacy
fixed-offset times), as a bare time when floating, or as a date for all-day
events, together with a `timezone` field describing the zone.

## Development

Tests use iCal text fixtures and never contact a CalDAV server. Run them with:

```sh
uv run --with pytest --with caldav --with icalendar --with tzdata pytest
```

## Tools

### Calendars

| Tool | Description |
|---|---|
| `list_calendars` | List all calendars on the server |
| `create_calendar` | Create a new calendar |
| `delete_calendar` | Delete a calendar by name |

### Events

| Tool | Description |
|---|---|
| `list_events` | List events in a calendar, optionally filtered by date range |
| `get_event` | Get a single event by UID |
| `create_event` | Create an event |
| `update_event` | Update an existing event's fields |
| `delete_event` | Delete an event by UID |

### Todos

| Tool | Description |
|---|---|
| `list_todos` | List todos in a calendar, optionally filtered by status |
| `create_todo` | Create a todo |
| `complete_todo` | Mark a todo as completed |
| `delete_todo` | Delete a todo by UID |

## License

AGPL-3.0. See [LICENSE](LICENSE).
