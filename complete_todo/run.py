#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers


def complete_if_pending(todo: object, uid: str) -> bool:
    """Complete a pending todo, returning True if it was already completed.

    A non-pending todo is never passed to caldav's complete(), which asserts
    the todo is pending. A cancelled todo is reported and exits instead. The
    check only uses the todo's own is_pending()/STATUS, so it can be tested
    with a fake todo object.
    """
    if not todo.is_pending():
        if str(todo.icalendar_component.get("STATUS", "")) == "CANCELLED":
            print(f"Todo is cancelled: {uid}", file=sys.stderr)
            sys.exit(1)
        return True
    # complete() sets STATUS=COMPLETED and stamps the COMPLETED datetime per
    # RFC 5545, preserving the DUE TZID.
    todo.complete()
    return False


def main() -> None:
    parameters = json.load(sys.stdin)
    helpers.validate_parameters(parameters, {"calendar_name", "uid"})
    calendar_name: str = parameters["calendar_name"]
    uid: str = parameters["uid"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, calendar_name)
    todo = calendar.todo_by_uid(uid)
    already_completed = complete_if_pending(todo, uid)

    print(
        json.dumps(
            {"uid": uid, "completed": True, "already_completed": already_completed}
        )
    )


if __name__ == "__main__":
    main()
