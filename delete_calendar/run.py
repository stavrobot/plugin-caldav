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
    helpers.validate_parameters(parameters, {"name"})
    name: str = parameters["name"]

    principal = helpers.get_principal()
    calendar = helpers.find_calendar_by_name(principal, name)
    calendar.delete()

    print(json.dumps({"deleted": True}))


main()
