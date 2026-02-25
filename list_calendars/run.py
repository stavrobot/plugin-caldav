#!/usr/bin/env -S uv run
# /// script
# dependencies = ["caldav"]
# ///

import json
import sys

sys.path.insert(0, "..")
import helpers


def main() -> None:
    principal = helpers.get_principal()
    calendars = principal.calendars()

    result = []
    for calendar in calendars:
        supported_components = list(calendar.get_supported_components())
        result.append(
            {
                "name": calendar.name,
                "url": str(calendar.url),
                "supported_components": supported_components,
            }
        )

    print(json.dumps(result))


main()
