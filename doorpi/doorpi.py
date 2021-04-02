"""The main DoorPi module housing the DoorPi class' implementation."""

from __future__ import annotations

import argparse
import datetime
import html
import itertools
import logging
import os
import pathlib
import signal
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any, cast

import doorpi
import doorpi.actions.snapshot
import doorpi.config
import doorpi.event.handler
import doorpi.keyboard.handler
import doorpi.metadata
import doorpi.mqtt
import doorpi.sipphone
import doorpi.status.status_class
import doorpi.status.systemd
import doorpi.web

LOGGER = cast(doorpi.DoorPiLogger, logging.getLogger(__name__))
DEADLY_SIGNALS_ABORT = 3

if __name__ == "__main__":
    raise RuntimeError("Use 'python -m doorpi' to start DoorPi")


class DoorPi:
    """The main DoorPi class that ties everything together."""

    config: doorpi.config.Configuration
    event_handler: doorpi.event.handler.EventHandler
    dpsd: doorpi.status.systemd.DoorPiSD
    keyboard: doorpi.keyboard.handler.KeyboardHandler
    mqtt: doorpi.mqtt.MQTTClient | None
    sipphone: doorpi.sipphone.abc.AbstractSIPPhone
    webserver: threading.Thread | None

    _base_path: pathlib.Path | None
    __deadlysignals: int
    __last_tick: float
    __prepared: bool
    __shutdown: bool

    @property
    def extra_info(self) -> Mapping[str, Any]:
        return self.event_handler.extra_info

    @property
    def status(self) -> doorpi.status.status_class.DoorPiStatus:
        return doorpi.status.status_class.DoorPiStatus(self)

    def get_status(
        self,
        modules: Sequence[str] | None = None,
        value: Sequence[str] = (),
        name: Sequence[str] = (),
    ) -> doorpi.status.status_class.DoorPiStatus:
        return doorpi.status.status_class.DoorPiStatus(self, modules, value, name)

    @property
    def base_path(self) -> pathlib.Path:
        if self._base_path is None:
            name = doorpi.metadata.distribution.metadata["Name"]
            base = pathlib.Path.home() / f"{name.lower()}.ini"
            if base.is_file():
                self._base_path = pathlib.Path.home()
            elif sys.platform == "linux":
                try:
                    base = pathlib.Path(os.environ["XDG_CONFIG_HOME"])
                except KeyError:
                    base = pathlib.Path.home() / ".config"
                self._base_path = base / name.lower()
            elif sys.platform == "win32":
                self._base_path = pathlib.Path(os.environ["APPDATA"]) / name
            else:
                self._base_path = pathlib.Path.home() / name.lower()
            LOGGER.info("Auto-selected BasePath %s", self._base_path)
        return self._base_path

    def __init__(self, args: argparse.Namespace) -> None:
        if hasattr(doorpi, "INSTANCE"):
            raise RuntimeError("Only one DoorPi instance can be created")
        doorpi.INSTANCE = self

        self.configfile = pathlib.Path(args.configfile)
        self.config = doorpi.config.Configuration()
        self.config.load_builtin_definitions()
        try:
            self.config.load(self.configfile)
        except FileNotFoundError:
            LOGGER.error(
                "No configuration file found at %s, using defaults",
                self.configfile,
            )

        try:
            self._base_path = self.config["base_path"]
        except KeyError:
            self._base_path = None

        self.event_handler = doorpi.event.handler.EventHandler()
        self.webserver = None

        self.__deadlysignals = 0
        self.__prepared = False
        self.__shutdown = False

        self.__last_tick = time.time()

    def doorpi_shutdown(self, time_until_shutdown: int = 0) -> None:
        """Tell DoorPi to shut down."""
        if time_until_shutdown > 0:
            time.sleep(time_until_shutdown)
        self.__shutdown = True

    def signal_shutdown(self, signum: int, stackframe: Any) -> None:
        """Handles signals considered deadly, like INT and TERM."""
        del stackframe
        self.__shutdown = True
        self.__deadlysignals += 1
        signame = signal.Signals(signum).name

        if self.__deadlysignals == 1:
            LOGGER.info("Caught deadly signal %s, shutting down", signame)
            return
        if self.__deadlysignals == 2:
            LOGGER.info("Caught deadly signal %s (2/3), forcing shutdown", signame)
            raise BaseException("Force-exiting due to signal")

        LOGGER.info(
            "Caught deadly signal %s (%d/3), aborting process",
            signame,
            self.__deadlysignals,
        )
        os._exit(255)

    def prepare(self) -> None:
        self.dpsd = doorpi.status.systemd.DoorPiSD()

        # setup signal handlers for HUP, INT, TERM
        handler = self.signal_shutdown
        signal.signal(signal.SIGHUP, handler)
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

        # register own events
        for event in (
            "BeforeStartup",
            "OnStartup",
            "AfterStartup",
            "BeforeShutdown",
            "OnShutdown",
            "AfterShutdown",
            "OnTimeTick",
            "OnTimeRapidTick",
        ):
            self.event_handler.register_event(event, __name__)

        # register base actions
        self.event_handler.register_action(
            "OnTimeTick", f"time_tick:{self.__last_tick}"
        )

        # register modules
        self.webserver = doorpi.web.load()
        self.keyboard = doorpi.keyboard.load()
        self.mqtt = doorpi.mqtt.load()
        self.sipphone = doorpi.sipphone.load()

        self.keyboard.start()
        self.sipphone.start()
        if self.mqtt:
            self.mqtt.start()

        self.__prepared = True

    def __del__(self) -> None:
        if self.__prepared:
            LOGGER.error(
                "DoorPi is being garbage collected,"
                " but was not properly shut down!\n"
                "This is a bug. Please report it to the author/s.\n"
                "Attempting to shutdown properly (errors may follow)"
            )
            self.destroy()

    def destroy(self) -> None:
        LOGGER.debug("Shutting down DoorPi")
        self.__shutdown = True
        self.dpsd.stopping()

        if not self.__prepared:
            return

        LOGGER.debug("Threads before starting shutdown: %s", self.event_handler.threads)

        self.event_handler.fire_event_sync("BeforeShutdown", __name__)
        self.event_handler.fire_event_sync("OnShutdown", __name__)
        self.event_handler.fire_event_sync("AfterShutdown", __name__)

        timeout = 5.0
        waiting_between_checks = 0.5

        while timeout > 0 and not self.event_handler.idle:
            LOGGER.debug(
                "Waiting %s seconds for %d events to finish",
                timeout,
                len(self.event_handler.threads),
            )
            LOGGER.trace("Still existing event threads: %s", self.event_handler.threads)
            LOGGER.trace("Still existing event sources: %s", self.event_handler.sources)
            time.sleep(waiting_between_checks)
            timeout -= waiting_between_checks

        if len(self.event_handler.sources) > 1:
            LOGGER.warning(
                "Some event sources did not shut down properly: %s",
                self.event_handler.sources[1:],
            )

        # unregister modules
        self.__prepared = False
        del self.sipphone, self.keyboard, self.mqtt, self.webserver

        del doorpi.INSTANCE
        LOGGER.info("======== DoorPi completed shutting down ========")

    def run(self) -> None:
        LOGGER.debug("run")
        if not self.__prepared:
            self.prepare()

        self.event_handler.fire_event_sync("BeforeStartup", __name__)
        self.event_handler.fire_event_sync("OnStartup", __name__)
        self.event_handler.fire_event_sync("AfterStartup", __name__)

        LOGGER.info("DoorPi started successfully")
        LOGGER.info("BasePath is %s", self.base_path)

        # setup watchdog ping and signal startup success
        self.event_handler.register_action(
            "OnTimeSecondOdd",
            doorpi.actions.CallbackAction(self.dpsd.watchdog),
        )
        self.dpsd.ready()

        tickrate = 0.05  # seconds between OnTimeRapidTick events
        tickrate_slow = 10  # rapid ticks between OnTimeTick events
        last = time.time()
        next_slowtick = 0.0

        while not self.__shutdown:
            self.event_handler.fire_event_sync("OnTimeRapidTick", __name__)
            next_slowtick -= 1

            if next_slowtick <= 0:
                self.__last_tick = time.time()
                self.event_handler.fire_event_sync("OnTimeTick", __name__)
                next_slowtick = tickrate_slow

            now = time.time()
            duration = now - last

            if duration > tickrate:
                skipped_ticks = duration // tickrate
                LOGGER.warning(
                    "Tick took too long (%.1fms > %.1fms), skipping %d tick(s)",
                    duration * 1000,
                    tickrate * 1000,
                    skipped_ticks,
                )
                LOGGER.warning(
                    "registered actions for OnTimeRapidTick: %s",
                    self.event_handler.actions["OnTimeRapidTick"],
                )
                LOGGER.warning(
                    "registered actions for OnTimeTick: %s",
                    self.event_handler.actions["OnTimeTick"],
                )
                last += skipped_ticks * tickrate
                next_slowtick -= skipped_ticks

            last += tickrate
            time.sleep(last - now)

    def parse_string(self, input_string: str) -> str:
        parsed_string = datetime.datetime.now().strftime(str(input_string))

        def format_table_row(key: Any, val: Any) -> str:
            key = html.escape(str(key))
            val = html.escape(str(val)).replace("\r\n", "\n").replace("\n", "<br>")
            return f"<tr><th>{key}</th><td>{val}</td></tr>"

        infos_as_html = "".join(
            itertools.chain(
                ("<table><tbody>",),
                itertools.starmap(format_table_row, self.extra_info.items()),
                ("</tbody></table>",),
            )
        )

        mapping_table = {
            "INFOS_PLAIN": str(self.extra_info),
            "INFOS": infos_as_html,
            "BASEPATH": str(self.base_path),
            "last_tick": str(self.__last_tick),
        }

        for key, val in doorpi.metadata.__dict__.items():
            if isinstance(val, str):
                mapping_table[key.upper()] = val

        if self.config:
            snapshots = doorpi.actions.snapshot.SnapshotAction.list_all()
            if snapshots:
                last_snapshot = os.fspath(snapshots[-1])
            else:
                last_snapshot = "- no snapshots -"
            mapping_table.update({"LAST_SNAPSHOT": last_snapshot})

        if self.keyboard:
            mapping_table.update(self.keyboard.enumerate_outputs())

        for key, val in mapping_table.items():
            parsed_string = parsed_string.replace(f"!{key}!", val)

        for key, val in self.extra_info.items():
            parsed_string = parsed_string.replace(f"!{key}!", str(val))

        return parsed_string
