"""The DoorPiWeb server."""

import asyncio
import http.server
import logging
import os
import pathlib
import socket
import threading
from typing import cast

import doorpi
from doorpi.actions import CallbackAction

LOGGER = cast(doorpi.DoorPiLogger, logging.getLogger(__name__))

try:
    from . import server
except ImportError as err:
    _MISSING_DEP = err.name

    # pylint: disable-next=useless-return
    def load() -> threading.Thread | None:
        """Load the webserver."""
        LOGGER.error(
            "Cannot start web server: Unmet dependencies: %s",
            _MISSING_DEP,
        )
        return None

else:

    def load() -> threading.Thread | None:
        """Load the webserver."""
        thread = threading.Thread(
            target=asyncio.run,
            args=(server.run(),),
            name="Webserver Thread",
        )
        eh = doorpi.INSTANCE.event_handler
        eh.register_event("OnWebServerStart", "doorpi.web")
        eh.register_event("OnWebServerStop", "doorpi.web")
        eh.register_action(
            "OnStartup", doorpi.actions.CallbackAction(thread.start)
        )
        return thread
