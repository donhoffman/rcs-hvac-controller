from typing import List
import json
import logging
import paho.mqtt.client as mqtt

from rcs_controller import RCSController
from zones import zones_by_index

logger = logging.getLogger("app.mqtt_client")


class MQTTClient(object):
    def __init__(
        self,
        rcs_ctrl: RCSController,
        host: str,
        port: int,
        user: str,
        password: str,
        topic_root: str,
        device_node_id: str,
        _tls: bool = False,
        _tls_insecure: bool = False,
        timeout_seconds: int = 60,
    ):
        self.topic_root = topic_root
        self.device_node_id = device_node_id
        self.device_topic_prefix = f"{topic_root}/climate/{self.device_node_id}"
        self.rcs_ctrl = rcs_ctrl
        self.timeout_seconds = timeout_seconds
        self.client = mqtt.Client()
        self.connected = False

        self.client.username_pw_set(user, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.reconnect_delay_set(self.timeout_seconds)
        try:
            self.client.connect(host, port, self.timeout_seconds)
            self.client.loop_start()
            logger.info(f"Connecting to MQTT server at {host}:{port}.")
        except Exception as e:
            logger.debug(f"Failed to connect to MQTT broker at {host}: {str(e)}")
            raise e

    def on_connect(self, client, _userdata, _flags, rc) -> None:
        if rc == 0:
            self.connected = True
            logger.debug("Connected to MQTT server.")

            # Send the entity configs
            self.publish_zone_configs()

            # Mark thermostat as offline until data is synced and published
            availability_topic = f"{self.device_topic_prefix}/availability"
            client.publish(availability_topic, payload="offline", retain=True)

            # Set Last Will message.
            client.will_set(availability_topic, payload="offline", qos=1, retain=True)

            # Subscribe to the command topic for all zones
            command_topic_root = f"{self.device_topic_prefix}/+/set"
            client.subscribe(command_topic_root)

            # Subscribe to the MQTT integration availability topic
            client.subscribe(f"{self.topic_root}/availability")
        else:
            self.connected = False
            logger.debug(f"Failed to connect to MQTT server result code {rc}.")

    def on_message(self, _client, _userdata, msg) -> None:
        if not self.connected:
            return

        # Check for MQTT integration availability message
        topic_parts: List[str] = msg.topic.split("/")
        if (
            len(topic_parts) == 2
            and topic_parts[0] == self.device_topic_prefix
            and topic_parts[1] == "availability"
        ):
            if msg.payload == "online":
                self.rcs_ctrl.force_sync()
            return

        # Else it may be command for thermostat
        if (
            (len(topic_parts) != 6)
            or (topic_parts[0] != self.topic_root)
            or (topic_parts[1] != "climate")
            or (topic_parts[2] != self.device_node_id)
            or (topic_parts[4] != "set")
        ):
            logger.error(f"Got message with malformed topic: {msg.topic}")
            return
        logger.debug(f"Got message with topic: {msg.topic}")
        logger.debug(f"Payload is: {msg.payload}")

        # Dispatch the message
        # Determine which entity
        entity = topic_parts[3]
        # TBD: validate entity
        # Determine command and dispatch

        command = topic_parts[5]
        match command:
            case "setpoint":
                logger.debug(f"Setting setpoint to: {msg.payload}")
                try:
                    target_setpoint = float(msg.payload)
                except ValueError:
                    logger.error(f"Bad setpoint payload: {msg.payload}")
                else:
                    self.rcs_ctrl.set_setpoint(entity, target_setpoint)
            case "mode":
                logger.debug(f"Setting mode to: {msg.payload}")
                if msg.payload not in ["off", "heat", "cool", "auto"]:
                    logger.error(f"Bad mode payload: {msg.payload}")
                    return
                self.rcs_ctrl.set_mode(entity, msg.payload)
            case _:
                logger.error(f"Unknown command: {command}")

    def on_disconnect(self, _client, _userdata, _rc) -> None:
        self.connected = False

    def publish_zone_configs(self):
        # Publish the device configuration for each zone

        if zones_by_index is None or len(zones_by_index) == 0:
            logger.error(f"No zones found for device '{self.device_node_id}'")
            return
        for zone in zones_by_index.values():
            zone_config = {
                "name": None,
                "device_class": "climate",
                "unique_id": f"{self.device_node_id}_{zone.entity_name}",
                "device": {"name": zone.name, "identifiers": [{self.device_node_id}]},
                "modes": ["off", "heat", "cool", "auto"],
                "optimistic": False,
                "precision": 1.0,
                "temperature_unit": "F",
                "temp_step": 1.0,
                "~": f"{self.device_topic_prefix}/{zone.entity_name}",
                "availability_topic": f"{self.device_topic_prefix}/availability/",
                "action_topic": "~/state",
                "action_template": "{{ value_json.action }}",
                "current_temperature_topic": "~/state",
                "current_temperature_template": "{{ value_json.temperature }}",
                "temperature_command_topic": "~/set/setpoint",
                "temperature_state_topic": "~/state",
                "temperature_state_template": "{{ value_json.setpoint }}",
                "mode_command_topic": "~/set/mode",
                "mode_state_topic": "~/state",
                "mode_state_template": "{{ value_json.mode }}",
            }
            config_topic = f"{self.device_topic_prefix}/config"
            self.client.publish(config_topic, json.dumps(zone_config))

    def publish_all_zone_status(self, force: bool = False):
        for zone in zones_by_index.values():
            if not zone.modified_since_last_sync and not force:
                logger.debug(f"Skipping update of zone '{zone.name}'")
                continue
            status_entry = {
                "setpoint": zone.current_setpoint,
                "mode": zone.current_mode,
                "temperature": zone.current_temperature,
                "action": zone.current_action,
            }
            status_topic = f"{self.device_topic_prefix}/status"
            self.client.publish(status_topic, json.dumps(status_entry))
            logger.debug(
                f"Published status for zone '{zone.name}': {json.dumps(status_entry)}"
            )
            zone.modified_since_last_sync = False
