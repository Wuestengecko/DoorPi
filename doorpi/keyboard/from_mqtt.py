"""The ``mqtt`` keyboard module for DoorPi."""

from __future__ import annotations

import importlib.metadata as imm
import json
import logging
import re
import time
from typing import Any

import paho.mqtt.client as mqtt

from . import abc

RETRY_INTERVAL = 15  # seconds
LOGGER = logging.getLogger(__name__)
DEFAULT_PORT = 1883
SLUG_RE = re.compile("[^a-zA-Z0-9_-]+")


# pylint: disable-next=too-many-instance-attributes
class MQTTKeyboard(abc.AbstractKeyboard):
    """The ``mqtt`` keyboard for DoorPi."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._nameslug = SLUG_RE.sub("-", name)
        self._input_states = dict.fromkeys(self._inputs, False)
        try:
            self._topic_prefix = self.config["topic_prefix"]
        except KeyError:
            self._topic_prefix = f"doorpi/{self._nameslug}"

        qos = self.config["qos"]
        if not 0 <= qos <= 2:
            raise ValueError(f"Invalid QoS level {qos}, must be 0, 1 or 2")

        self._button_inputs = set(self.config["button_inputs"])
        self._trigger_outputs = set(self.config["trigger_outputs"])

        if bad_pins := set(self._button_inputs) - set(self._inputs):
            raise ValueError(f"Invalid names in 'button_inputs': {bad_pins}")
        if bad_pins := set(self._trigger_outputs) - set(self._outputs):
            raise ValueError(f"Invalid names in 'trigger_outputs': {bad_pins}")

        self.__availability_topic = f"{self._topic_prefix}/status"
        self.__client = client = mqtt.Client(
            client_id=self.config["client_id"]
        )
        client.will_set(f"{self._topic_prefix}/status", "offline", retain=True)
        self.__did_connect = False
        self.__connect_time = time.time()
        self.__try_connect()

    def __try_connect(self) -> None:
        client = self.__client
        broker, _, port_ = self.config["broker"].partition(":")
        port = int(port_ or DEFAULT_PORT)

        try:
            client.connect(broker, port)
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.error(
                "Failed to connect to broker, will retry in %ds",
                RETRY_INTERVAL,
            )
            return
        client.loop_start()

        if self.config["homeassistant"]:
            self.__publish_discovery()

        topic = f"{self._topic_prefix}/input/+"
        LOGGER.debug("Subscribing to %r", topic)
        self.__client.subscribe(topic)
        self.__client.message_callback_add(topic, self.__on_pin_message)

        self.publish_message(self.__availability_topic, "online")
        self.__did_connect = True

    def _deactivate(self) -> None:
        self.publish_message(self.__availability_topic, "offline")
        self.__client.disconnect()
        self.__client.loop_stop()

    def publish_message(
        self, topic: str, payload: str | bytes, retain: bool = True
    ) -> None:
        LOGGER.debug("Publishing to %r: %r", topic, payload)
        self.__client.publish(
            topic, payload, qos=self.config["qos"], retain=retain
        ).wait_for_publish()

    def publish_json(
        self, topic: str, payload: object, retain: bool = True
    ) -> None:
        self.publish_message(
            topic,
            json.dumps(payload, separators=(",", ":")),
            retain=retain,
        )

    def __publish_discovery(self) -> None:
        config_device = {
            "identifiers": [f"doorpi_{self._nameslug}"],
            "model": "DoorPi MQTT Keyboard",
            "name": f"DoorPi {self.name}",
            "sw_version": imm.version("doorpi"),
        }
        for name in self.inputs:
            slug = SLUG_RE.sub("-", name)
            cfg: dict[str, Any] = {
                "unique_id": f"doorpi_{self._nameslug}/{slug}",
                "name": name,
                "command_topic": f"{self._topic_prefix}/input/{slug}",
                "device": config_device,
                "availability_topic": self.__availability_topic,
            }
            if name in self._button_inputs:
                etype = "button"
                cfg |= {
                    "payload_press": "ON",
                }
            else:
                etype = "switch"
                cfg |= {
                    "state_topic": cfg["command_topic"],
                }

            conftopic = f"homeassistant/{etype}/{cfg['unique_id']}/config"
            self.publish_json(conftopic, cfg)
            if etype == "switch":
                self.publish_message(cfg["command_topic"], "OFF")

        for name in self._outputs:
            slug = SLUG_RE.sub("-", name)
            if name in self._trigger_outputs:
                etype = "event"
                cfg = {
                    "unique_id": f"doorpi_{self._nameslug}/{slug}",
                    "name": name,
                    "event_types": ["press"],
                    "state_topic": f"{self._topic_prefix}/output/{slug}",
                    "value_template": '{"event_type": "press"}',
                    "device": config_device,
                }
            else:
                etype = "binary_sensor"
                cfg = {
                    "unique_id": f"doorpi_{self._nameslug}/{slug}",
                    "state_topic": f"{self._topic_prefix}/output/{slug}",
                    "name": name,
                    "device": config_device,
                    "availability_topic": self.__availability_topic,
                }
                self.publish_message(cfg["state_topic"], "OFF")
            conftopic = f"homeassistant/{etype}/{cfg['unique_id']}/config"
            self.publish_json(conftopic, cfg)

    def __on_pin_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        del client, userdata
        prefix = f"{self._topic_prefix}/input/"
        if not message.topic.startswith(prefix):
            LOGGER.warning("Ignoring unsolicited message on %r", message.topic)
            return

        pin = message.topic[len(prefix) :]
        if "/" in pin:
            LOGGER.warning("Ignoring message with invalid pin name %s", pin)
            return

        if pin not in self._inputs:
            LOGGER.warning("Ignoring message for unknown pin %s", pin)
            return

        try:
            payload = message.payload.decode("utf-8")
        except UnicodeDecodeError:
            LOGGER.error(
                "Ignoring invalid payload for pin %s: %r", pin, message.payload
            )
            return

        value = self._normalize(payload)
        LOGGER.debug("Received input for pin %s: %r", pin, value)

        if pin in self._button_inputs:
            if not value:
                LOGGER.info("Ignoring OFF command for button input %s", pin)
                return
            self._fire_event("OnKeyPressed", pin)
            return

        if value == self._input_states[pin]:
            LOGGER.debug(
                "Ignoring duplicate %s command for input pin %s",
                ("OFF", "ON")[value],
                pin,
            )
            return

        self._input_states[pin] = value
        if value:
            self._fire_keydown(pin)
        else:
            self._fire_keyup(pin)

    def self_check(self) -> None:
        if not self.__did_connect:
            now = time.time()
            if now > self.__connect_time + RETRY_INTERVAL:
                LOGGER.info("Retrying connection to the MQTT broker")
                self.__try_connect()
                self.__connect_time = now

    def input(self, pin: str) -> bool:
        if pin not in self._inputs:
            raise ValueError(f"No MQTT input with name {self.name}.{pin}")
        return self._input_states[pin]

    def output(self, pin: str, value: Any) -> bool:
        if pin not in self._outputs:
            raise ValueError(f"No MQTT output with name {self.name}.{pin}")

        value = self._normalize(value)
        trigger = pin in self._trigger_outputs
        if trigger and not value:
            LOGGER.info("Ignoring OFF command for trigger output %s", pin)

        payload = ("OFF", "ON")[value]
        if value == self._outputs[pin]:
            LOGGER.debug(
                "Ignoring duplicate %r command for output pin %s", payload, pin
            )
            return True
        self.publish_message(
            f"{self._topic_prefix}/output/{pin}",
            payload,
            retain=not trigger or self.config["trigger_retain"],
        )
        if not trigger:
            self._outputs[pin] = value
        return True
