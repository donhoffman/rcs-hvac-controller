from typing import Final
import os
import argparse
import yaml
import logging

from rcs_controller import RCSController
from mqtt_client import MQTTClient
from zones import create_zones_from_config

VERSION: Final = "1.0.0"
DEFAULT_MQTT_PORT: Final = 1883
LOG_FORMAT: Final = "%(asctime)s - %(module)s - %(levelname)s - %(message)s"


def main() -> int:
    parser = argparse.ArgumentParser(description="RCS HVAC Controller")

    parser.add_argument(
        "--config",
        type=str,
        help="Full path to controller/zone config file",
        default=os.getenv("CONFIG", "/config/config.yml"),
    )
    parser.add_argument(
        "--log-level",
        type=str,
        help="Logging level",
        default=os.getenv("LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "--serial", type=str, help="Serial port", default=os.getenv("SERIAL", None)
    )
    parser.add_argument(
        "--mqtt-host",
        type=str,
        help="MQTT host",
        default=os.getenv("MQTT_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        help="MQTT port number",
        default=os.getenv("MQTT_PORT", DEFAULT_MQTT_PORT),
    )
    parser.add_argument(
        "--mqtt-user",
        type=str,
        help="MQTT user name",
        default=os.getenv("MQTT_USER", None),
    )
    parser.add_argument(
        "--mqtt-password",
        type=str,
        help="MQTT password",
        default=os.getenv("MQTT_PASSWORD", None),
    )
    parser.add_argument(
        "--mqtt-topic-root",
        type=str,
        help="Root topic for MQTT Client publishing",
        default=os.getenv("TOPIC_ROOT", "homeassistant"),
    )
    args = parser.parse_args()

    logging.basicConfig(format=LOG_FORMAT, level=args.log_level)
    logger = logging.getLogger(__name__)

    # Parse device/zone config file and create zones
    try:
        with open(args.config, "r") as f:
            zones_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Zone config file not found: {args.config}")
        return 1
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config file: {str(e)}")
        return 1
    if not create_zones_from_config(zones_config):
        logger.error("Zone configuration error")
        return 1

    logger.info("Starting RCS HVAC Controller - %s" % VERSION)

    logger.debug("Activating RCS controller.")
    device_node_id: str = zones_config.get("device_node_id")
    if device_node_id is None:
        logger.error("Device node id not found in config file.  Required.")
        return 1
    try:
        controller = RCSController(args.serial)
        mqtt = MQTTClient(
            controller,
            args.mqtt_host,
            args.mqtt_port,
            args.mqtt_user,
            args.mqtt_password,
            topic_root=args.mqtt_topic_root,
            device_node_id=device_node_id,
            version=VERSION,
        )
    except Exception as e:
        logger.error(f"Failed to initialize RCS controller: {str(e)}")
        return -1

    # Activate controller loop
    code = controller.control_loop(mqtt)
    return code


if __name__ == "__main__":
    rc = main()
    exit(rc)
