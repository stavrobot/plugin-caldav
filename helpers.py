import json
import sys

import caldav


def get_principal() -> caldav.Principal:
    # Tools run from their own subdirectory, so ../config.json resolves to
    # the plugin root's config.json regardless of where helpers.py lives.
    with open("../config.json") as config_file:
        config = json.load(config_file)

    client = caldav.DAVClient(
        url=config["server_url"],
        username=config["username"],
        password=config["password"],
    )
    return client.principal()


def find_calendar_by_name(
    principal: caldav.Principal, name: str
) -> caldav.Calendar:
    calendars = principal.calendars()
    for calendar in calendars:
        if calendar.name == name:
            return calendar
    print(f"Calendar not found: {name}", file=sys.stderr)
    sys.exit(1)
