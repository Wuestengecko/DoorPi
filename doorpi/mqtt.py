from __future__ import annotations

import abc
import importlib
import importlib.metadata as imm
import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

import doorpi
from doorpi.actions import CallbackAction

DEFAULT_PORT = 1883
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    import paho.mqtt.client as mqtt

    def load() -> MQTTClient | None: ...

else:
    mqtt = None

    def load() -> MQTTClient | None:
        global mqtt
        try:
            doorpi.INSTANCE.config["mqtt.broker"]
        except KeyError:
            LOGGER.debug("MQTT status updates not enabled")
            return None
        else:
            LOGGER.info("Loading MQTT client for status updates")
            mqtt = importlib.import_module("paho.mqtt.client")
            return MQTTClient()


class MQTTClient:
    """The DoorPi MQTT client component."""

    def __init__(self) -> None:
        self.config = doorpi.INSTANCE.config.view("mqtt")
        self.topic_prefix = self.config["topic_prefix"]
        self.client = mqtt.Client(
            client_id=self.config["client_id"],
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.will_set(f"{self.topic_prefix}/status", "offline", retain=True)

        broker, _, port_ = self.config["broker"].partition(":")
        port = int(port_ or DEFAULT_PORT)
        self.client.connect(broker, port)
        self.client.loop_start()

        self.__discovery = self.config["homeassistant"]
        self.__components = [
            _SIPPhoneName(self),
            _ActiveCall(self),
            _Hangup(self),
            _ReloadConfig(self),
        ]
        self.__services = [
            _ExecuteAction(self),
        ]
        # AfterShutdown because a keyboard might be using our connection
        doorpi.INSTANCE.event_handler.register_action(
            "AfterShutdown", CallbackAction(self.stop)
        )

    def start(self) -> None:
        """Start the component."""
        if self.__discovery:
            self.__publish_discovery()

        for comp in self.__components:
            comp.start()
        for svc in self.__services:
            svc.start()

        self.publish(f"{self.topic_prefix}/status", "online")

    def stop(self) -> None:
        self.publish(f"{self.topic_prefix}/status", "offline")
        self.client.disconnect()
        self.client.loop_stop()

    def __build_publish_common(self) -> dict[str, Any]:
        return {
            "device": {
                "identifiers": ["doorpi___status__"],
                "model": "DoorPi",
                "name": "DoorPi",
                "sw_version": imm.version("doorpi"),
            },
            "availability_topic": f"{self.topic_prefix}/status",
        }

    def __publish_discovery(self) -> None:
        # TODO add web interface URL to device info
        config_common = self.__build_publish_common()

        for comp in self.__components:
            self.__discover(comp, config_common)

    def rediscover(
        self,
        comp: _Component,
        /,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        if not self.__discovery:
            return
        overrides = overrides or {}
        self.__discover(comp, overrides | self.__build_publish_common())

    def __discover(self, comp: _Component, overrides: dict[str, Any]) -> None:
        unique_id = f"doorpi___status__/{comp.id}"
        topic = f"homeassistant/{comp.type}/{unique_id}/config"
        payload = comp.build_discovery() | overrides | {"unique_id": unique_id}
        self.publish_json(topic, payload)

    def publish_json(self, topic: str, payload: Any, *, retain: bool = True) -> None:
        payload = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
        self.publish(topic, payload, retain=retain)

    def publish(self, topic: str, payload: str, *, retain: bool = True) -> None:
        LOGGER.debug("Publishing to %r: %r", topic, payload)
        self.client.publish(topic, payload, qos=self.config["qos"], retain=retain)

    def subscribe(
        self,
        topic: str,
        callback: Callable[[mqtt.MQTTMessage], None],
    ) -> None:
        self.client.subscribe(topic)
        self.client.message_callback_add(topic, lambda _1, _2, m: callback(m))


class _Component:
    type: ClassVar[str]
    """The Home Assistant entity type that this component exposes."""
    id: ClassVar[str]
    """The "unique ID" of this entity."""

    @property
    def _topic(self) -> str:
        return f"{self._client.topic_prefix}/{self.id}"

    def __init__(self, client: MQTTClient) -> None:
        self._client = client

    @abc.abstractmethod
    def build_discovery(self) -> dict[str, Any]:
        """Build the component-specific parts of the discovery payload.

        Returns:
            The discovery payload as JSON encodable dictionary.

            The following fields are automatically generated by the
            parent MQTTClient and should not be added:

            - *availability_topic*
            - *device*
            - *unique_id* - built from the 'id' class variable.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def start(self) -> None:
        """Start the component.

        In this method, components should subscribe to relevant events and publish the
        first status message. This is called once during startup, after publishing
        discovery messages (if enabled) and before announcing to be online.
        """


class _SIPPhoneName(_Component):
    type = "sensor"
    id = "sipphone_name"

    def build_discovery(self) -> dict[str, Any]:
        return {
            "icon": "mdi:phone-voip",
            "name": "SIP Phone name",
            "entity_category": "diagnostic",
            "state_topic": f"{self._topic}",
        }

    def start(self) -> None:
        name = doorpi.INSTANCE.sipphone.get_name()
        self._client.publish(self._topic, name)


class _ActiveCall(_Component):
    type = "sensor"
    id = "sipphone_activecall"

    def build_discovery(self) -> dict[str, Any]:
        return {
            "icon": "mdi:phone-hangup",
            "name": "Active Call",
            "device_class": "enum",
            "options": ["inactive", "ringing", "connected"],
            "state_topic": self._topic,
            "value_template": "{{value_json.state}}",
            "json_attributes_template": "{{value}}",
        }

    def start(self) -> None:
        self._client.publish_json(self._topic, {"state": "inactive"})
        eh = doorpi.INSTANCE.event_handler
        eh.register_action("OnCallOutgoing", CallbackAction(self.__ringing))
        eh.register_action("OnCallConnect_S", CallbackAction(self.__connected))
        eh.register_action("OnCallUnanswered", CallbackAction(self.__disconnected))
        eh.register_action("OnCallDisconnect", CallbackAction(self.__disconnected))

    def __disconnected(self) -> None:
        self._client.publish_json(self._topic, {"state": "inactive"})
        self._client.rediscover(self)

    def __ringing(self) -> None:
        self._client.publish_json(
            self._topic, {"state": "ringing", "direction": "outgoing"}
        )
        self._client.rediscover(self, {"icon": "mdi:phone-ring"})

    def __connected(self) -> None:
        info = doorpi.INSTANCE.sipphone.dump_call()
        info.pop("total_time", None)
        assert info["direction"] in {"incoming", "outgoing"}
        icon = "mdi:phone-" + info["direction"]
        self._client.publish_json(self._topic, {"state": "connected", **info})
        self._client.rediscover(self, {"icon": icon})


class _Uptime(_Component):
    type = "sensor"
    id = "uptime"

    __starttime: float

    def build_discovery(self) -> dict[str, Any]:
        return {
            "icon": "mdi:timer-outline",
            "name": "Uptime",
            "entity_category": "diagnostic",
            "state_class": "total_increasing",
            "expire_after": 30,
            "state_topic": self._topic,
            "unit_of_measurement": "s",
        }

    def start(self) -> None:
        self.__starttime = int(time.monotonic())
        self._client.publish(self._topic, "0")
        doorpi.INSTANCE.event_handler.register_action(
            "OnTimeSecond", CallbackAction(self.__update)
        )

    def __update(self) -> None:
        self._client.publish(self._topic, str(int(time.time()) - self.__starttime))


class _Hangup(_Component):
    type = "button"
    id = "sipphone_hangup"

    def build_discovery(self) -> dict[str, Any]:
        return {
            "icon": "mdi:phone-hangup",
            "name": "Hangup",
            "command_topic": self._topic,
        }

    def start(self) -> None:
        self._client.subscribe(self._topic, self.__pressed)

    def __pressed(self, _: mqtt.MQTTMessage, /) -> None:
        doorpi.INSTANCE.sipphone.hangup()


class _ReloadConfig(_Component):
    type = "button"
    id = "config_reload"

    def build_discovery(self) -> dict[str, Any]:
        return {
            "name": "Reload configuration",
            "device_class": "restart",
            "entity_category": "config",
            "command_topic": self._topic,
        }

    def start(self) -> None:
        self._client.subscribe(self._topic, self.__pressed)

    def __pressed(self, _: mqtt.MQTTMessage, /) -> None:
        doorpi.INSTANCE.config.load(doorpi.INSTANCE.configfile)


class _Service:
    id: ClassVar[str]

    @property
    def _topic(self) -> str:
        return f"{self._client.topic_prefix}/{self.id}"

    def __init__(self, client: MQTTClient) -> None:
        self._client = client

    def start(self) -> None:
        self._client.subscribe(self._topic, self.__callback)

    def __callback(self, msg: mqtt.MQTTMessage, /) -> None:
        try:
            response = self.execute(msg.payload.decode())
        except Exception as err:
            self._client.publish_json(
                f"{msg.topic}/response",
                {"ok": False, "error": f"{type(err).__name__}: {err}"},
                retain=False,
            )
        else:
            try:
                json_response = json.dumps(response)
            except Exception:
                json_response = "null"
            self._client.publish(
                f"{msg.topic}/response",
                f'{{"ok":true,"response":{json_response}}}',
                retain=False,
            )

    @abc.abstractmethod
    def execute(self, payload: str, /) -> Any:
        """Execute the service."""


class _ExecuteAction(_Service):
    id = "exec_action"

    def execute(self, payload: str, /) -> None:
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, UnicodeError):
            extra = {}
        else:
            action = decoded["action"]
            extra = decoded.get("extra", {})
        action = doorpi.actions.from_string(payload)
        if action is None:
            raise ValueError("Invalid action string")
        action("_MQTT_", extra)
