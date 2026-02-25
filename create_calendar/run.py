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
    name: str = parameters["name"]
    supported_components: list[str] = [
        component.strip()
        for component in parameters.get(
            "supported_components", "VEVENT,VTODO"
        ).split(",")
    ]

    principal = helpers.get_principal()
    calendar = principal.make_calendar(
        name=name, supported_calendar_component_set=supported_components
    )

    print(json.dumps({"name": calendar.name, "url": str(calendar.url)}))


main()
