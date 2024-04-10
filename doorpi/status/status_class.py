from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Sequence
from typing import Any

import doorpi.doorpi

LOGGER = logging.getLogger(__name__)

MODULES = (
    "status_time",
    # "additional_informations",
    "config",
    "keyboard",
    "sipphone",
    "event_handler",
    "history_event",
    "history_snapshot",
    # "history_action",
    "environment",
    "webserver",
)


class DoorPiStatus:
    @property
    def json(self) -> str:
        return json.dumps(self.dictionary)

    @property
    def json_beautified(self) -> str:
        return json.dumps(self.dictionary, sort_keys=True, indent=4)

    def __init__(
        self,
        doorpi_obj: doorpi.doorpi.DoorPi,
        modules: Sequence[str] | None = None,
        value: Sequence[str] = (),
        name: Sequence[str] = (),
    ) -> None:
        if not modules:
            modules = MODULES
        self.dictionary: dict[str, dict[str, Any]] = {}

        if len(modules) == 0:
            modules = MODULES

        for module in modules:
            if module not in MODULES:
                LOGGER.warning("Skipping unknown status module %s", module)
                continue
            try:
                mod = importlib.import_module(
                    f"doorpi.status.status_lib.{module}"
                )
                self.dictionary[module] = mod.get(
                    doorpi_obj=doorpi_obj, name=name, value=value
                )
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception(
                    "Cannot collect status information for %s", module
                )
                self.dictionary[module] = {
                    "Error": f"Could not collect information about {module}"
                }


collect_status = DoorPiStatus  # pylint: disable=invalid-name
