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
    todo = calendar.todo_by_uid(uid)
    # complete() sets STATUS=COMPLETED and stamps the COMPLETED datetime per RFC 5545.
    todo.complete()

    print(json.dumps({"uid": uid, "completed": True}))


main()
