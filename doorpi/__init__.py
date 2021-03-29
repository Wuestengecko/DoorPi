"""Provide intercomstation to the doorstation by VoIP."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from . import doorpi

__all__: list[str] = []

INSTANCE: "doorpi.DoorPi"

TRACE_LEVEL = 5
logging.TRACE = TRACE_LEVEL  # type: ignore[attr-defined]
logging.addLevelName(TRACE_LEVEL, "TRACE")


class DoorPiLogger(logging.getLoggerClass()):  # type: ignore[misc]
    """Logger subclass that adds the TRACE level."""

    def trace(self, message: str, *args: Any, **kw: Any) -> None:
        """Logs with TRACE level."""
        if self.isEnabledFor(TRACE_LEVEL):  # pragma: no cover
            self._log(TRACE_LEVEL, message, args, **kw)


logging.setLoggerClass(DoorPiLogger)
