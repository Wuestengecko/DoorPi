import operator
from collections.abc import Iterable
from typing import Any

import doorpi.doorpi


def get(
    doorpi_obj: doorpi.doorpi.DoorPi,
    name: Iterable[str],
    value: Iterable[str],
) -> dict[str, Any]:
    del value
    status_getters = {
        "name": operator.methodcaller("get_name"),
        "current_call": operator.methodcaller("dump_call"),
    }
    return {
        n: status_getters[n](doorpi_obj.sipphone)
        for n in name
        if n in status_getters
    }


def is_active(doorpi_object: doorpi.doorpi.DoorPi) -> bool:
    return bool(doorpi_object.sipphone)
