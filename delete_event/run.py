#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers


def main() -> None:
    parameters = json.load(sys.stdin)
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    event = calendar.event_by_uid(uid)
    event.delete()

    print(json.dumps({"deleted": True}))


main()
