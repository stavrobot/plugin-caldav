# CalDAV plugin for Stavrobot

Manage calendars, events, and todos on any CalDAV server.

## Installation

Ask Stavrobot:

> Install the plugin at https://github.com/stavrobot/plugin-caldav.git

Then configure it with your CalDAV server credentials:

- **server_url**: Your CalDAV server base URL (e.g. `https://caldav.example.com`)
- **username**: Username for authentication
- **password**: Password for authentication

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
