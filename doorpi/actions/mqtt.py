"""MQTT related actions: mqtt_publish."""

from collections.abc import Mapping
from typing import Any

import doorpi
import doorpi.keyboard.from_mqtt as kb_mqtt

from . import Action, CheckAction


class MQTTPublishAction(Action):
    keyboard: kb_mqtt.MQTTKeyboard
    topic: str
    payload: str

    def __init__(self, *args: str) -> None:
        super().__init__()

        match args:
            case ("RETAIN", k, t, *p):
                self.retain = True
                kbname, topic, payload = k, t, ",".join(p)
            case (k, t, *p):
                self.retain = False
                kbname, topic, payload = k, t, ",".join(p)
            case _:
                raise ValueError("Invalid arguments")

        def late_init() -> None:
            keyboard = doorpi.INSTANCE.keyboard.get_keyboard(kbname)
            if not isinstance(keyboard, kb_mqtt.MQTTKeyboard):
                raise ValueError("Specified keyboard is not an MQTTKeyboard")
            if not topic:
                raise ValueError("No MQTT topic specified")
            if not payload:
                raise ValueError("No MQTT message payload specified")

            self.keyboard = keyboard
            self.topic = topic
            self.payload = payload

        doorpi.INSTANCE.event_handler.register_action(
            "BeforeStartup", CheckAction(late_init), oneshot=True
        )

    def __call__(self, event_id: str, extra: Mapping[str, Any]) -> None:
        del event_id, extra
        payload = doorpi.INSTANCE.parse_string(self.payload)
        self.keyboard.publish_message(self.topic, payload, retain=self.retain)

    def __str__(self) -> str:
        return (
            f"Publish {self.payload!r} to MQTT topic {self.topic!r}"
            + " as retained message" * self.retain
        )

    def __repr__(self) -> str:
        return (
            "mqtt_publish:"
            f"{self.keyboard.name},"
            f"{'RETAIN,' * self.retain}"
            f"{self.topic},"
            f"{self.payload}"
        )
