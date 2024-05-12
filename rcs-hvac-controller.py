from typing import Final
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
        "--config", type=str, help="Full path to controller/zone config file"
    )
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")
    parser.add_argument("--serial", type=str, help="Serial port", required=True)
    parser.add_argument("--mqtt-host", type=str, default="127.0.0.1", help="MQTT host")
    parser.add_argument(
        "--mqtt-port", type=int, default=DEFAULT_MQTT_PORT, help="MQTT port number"
    )
    parser.add_argument("--mqtt-user", type=str, help="MQTT user name")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password")
    parser.add_argument(
        "--mqtt-topic-root", type=str, help="Root topic for MQTT Client publishing"
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
