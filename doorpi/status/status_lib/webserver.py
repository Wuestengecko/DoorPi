import operator
from collections.abc import Callable, Iterable
from typing import Any

import doorpi.doorpi


def get(
    doorpi_obj: doorpi.doorpi.DoorPi,
    name: Iterable[str],
    value: Iterable[str],
) -> dict[str, Any]:
    del value
    status_getters: dict[str, Callable[[Any], Any]] = {
        "config_status": lambda _: {"infos": [], "warnings": [], "errors": []},
        "session_ids": lambda ws: list(ws.sessions.sessions),
        "sessions": operator.attrgetter("sessions.sessions"),
        "running": bool,
        "server_name": operator.attrgetter("server_name"),
        "server_port": operator.attrgetter("server_port"),
    }
    if not name:
        name = status_getters.keys()
    if doorpi_obj.webserver is None:
        return dict.fromkeys(name, None)
    else:
        return {
            n: status_getters[n](doorpi_obj.webserver)
            for n in name
            if n in status_getters
        }


def is_active(doorpi_object: doorpi.doorpi.DoorPi) -> bool:
    return bool(doorpi_object.webserver)
