from __future__ import annotations

import glob
import logging
import threading
from typing import Any, Literal

from gpiod import Chip
from gpiod.edge_event import EdgeEvent
from gpiod.exception import ChipClosedError, RequestReleasedError
from gpiod.line import Bias, Direction, Edge, Value
from gpiod.line_settings import LineSettings

import doorpi

from .abc import AbstractKeyboard
from .enums import GPIOPull

LOGGER = logging.getLogger(__name__)


class GPIODKeyboard(AbstractKeyboard):
    def __init__(self, name: str) -> None:
        super().__init__(name)

        self.__chip = Chip(_findchip(self.config["chip"]))

        pull = self.config["pull_up_down"]
        if pull is GPIOPull.OFF:
            bias = Bias.DISABLED
        elif pull is GPIOPull.UP:
            bias = Bias.PULL_UP
        elif pull is GPIOPull.DOWN:
            bias = Bias.PULL_DOWN
        else:
            raise ValueError(f"Unknown GPIO pull value: {pull.name}")

        LOGGER.info(
            "Requesting %d input and %d output lines with %.2fs debounce",
            len(self._inputs),
            len(self._outputs),
            self._bouncetime.total_seconds(),
        )
        self.__lines = self.__chip.request_lines(
            {
                tuple(self._inputs): LineSettings(
                    direction=Direction.INPUT,
                    edge_detection=Edge.BOTH,
                    bias=bias,
                    debounce_period=self._bouncetime,
                ),
                tuple(self._outputs): LineSettings(
                    direction=Direction.OUTPUT,
                    output_value=(
                        Value.INACTIVE if self._high_polarity else Value.ACTIVE
                    ),
                ),
            },
            consumer=f"DoorPi keyboard {self.name}",
        )
        if len(self.__lines.lines) != len(self._inputs) + len(self._outputs):
            raise RuntimeError(
                f"Wrong number of GPIO lines, requested"
                f" {len(self._inputs) + len(self._outputs)},"
                f" received {len(self.__lines.lines)}"
            )
        LOGGER.debug("Received access to lines: %s", self.__lines.lines)
        self.__offset2line = {
            o: str(l) for o, l in zip(self.__lines.offsets, self.__lines.lines)
        }
        self._input_states = dict.fromkeys(self._inputs, False)

        self.__waitthread = threading.Thread(
            target=self.__eventthread,
            name=f"GPIO events for keyboard {self.name}",
        )
        self.__waitthread.start()

    def _deactivate(self) -> None:
        self.__lines.release()
        self.__chip.close()
        self.__waitthread.join(1)

    def __eventthread(self) -> None:
        LOGGER.debug("GPIO worker thread started")
        try:
            while True:
                if not self.__lines.wait_edge_events(0.2):
                    continue

                (ev,) = self.__lines.read_edge_events(1)
                LOGGER.debug("Received edge event: %s", ev)
                pin = self.__offset2line[ev.line_offset]
                rising = ev.event_type is EdgeEvent.Type.RISING_EDGE
                self._input_states[pin] = new_state = self._normalize(rising)
                if new_state:
                    self._fire_keydown(pin)
                else:
                    self._fire_keyup(pin)
        except (RequestReleasedError, ChipClosedError):
            LOGGER.debug("Chip closed, exiting event thread")
        except BaseException:
            LOGGER.critical("GPIO worker thread crashed", exc_info=True)
            doorpi.INSTANCE.doorpi_shutdown()

    def self_check(self) -> None:
        if not self.__waitthread.is_alive():
            raise RuntimeError("GPIO event thread died")

    def input(self, pin: str) -> bool:
        super().input(pin)
        return self._input_states[pin]

    def output(self, pin: str, value: Any) -> Literal[True]:
        value = self._normalize(value)
        pinval = (Value.INACTIVE, Value.ACTIVE)[value]
        LOGGER.debug("Setting pin %s to value %s", pin, pinval.name)
        self.__lines.set_value(pin, pinval)
        return True


def _findchip(label: str) -> str:
    """Find a chip device by label."""
    for i in glob.glob("/dev/gpiochip*"):
        with Chip(i) as chip:
            if label == chip.get_info().label:
                LOGGER.info(
                    "Found GPIO chip %s at %s (%d lines)",
                    label,
                    i,
                    chip.get_info().num_lines,
                )
                return i
    raise ValueError(f"Cannot find a GPIO chip with label: {label}")
