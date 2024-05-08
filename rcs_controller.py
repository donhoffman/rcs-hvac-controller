import logging
from threading import Lock
from time import sleep
from typing import Final

import serial

from mqtt_client import MQTTClient
import zones

logger = logging.getLogger("app.rcs_controller")

# The target device is an RCS ZC6R that supports version 3.7 of the serial protocol. Only the first three zones are in
# use, but the code should generally support the full 6 zones. Serial connection type is RS-232 with baud rate of
# 9600 bps. Project is written to Python 3.12 or later.


class RCSController(object):

    TARGET_HVAC_DEVICE: Final[str] = "ZC6R"
    SLEEP_BETWEEN_COMMS: Final[float] = 0.011

    MODE_MAP_MQTT2RCS: Final[dict] = {
        "off": "O",
        "heat": "H",
        "cool": "C",
        "auto": "A",
    }
    MODE_MAP_RCS2MQTT: Final[dict] = {
        "O": "off",
        "H": "heat",
        "C": "cool",
        "A": "Auto",
        "I": None,
    }

    ZONE_ID_PREFIX: Final = b"Z="
    TEMP_PREFIX: Final = b"T="
    SETPOINT_PREFIX: Final = b"SP="
    MODE_PREFIX: Final = b"M="
    FAN_MODE_PREFIX: Final = b"FM="
    HEAT_CALL_PREFIX: Final = b"H1A="
    DAMPER_STATUS_PREFIX: Final = b"D"

    def __init__(self, serial_path: str):
        self.serial_path = serial_path
        self.conn = serial.Serial(serial_path, 9600, timeout=1, write_timeout=1)
        self.conn_lock = Lock()
        self.first_pass = True
        self.mqtt: MQTTClient | None = None

    def __del__(self):
        if self.conn is not None:
            self.conn.close()

    def control_loop(self, mqtt: MQTTClient) -> int:

        logger.debug("RCSController started")
        self.mqtt = mqtt

        try:
            while True:
                if not self._get_all_zone_status():
                    break
                self.mqtt.publish_all_zone_status(self.first_pass)
                self.first_pass = False
                sleep(15)
        except Exception as e:
            logger.info(f"RCSController received exception: {str(e)}")
            rc = 1
        else:
            rc = 0
        finally:
            self.conn.close()
            self.conn = None
        return rc

    def set_setpoint(self, entity: str, setpoint: float):
        if not self.conn or not self.conn.is_open:
            return
        if setpoint < 40 or setpoint > 99:
            return
        zone = zones.get_zone_by_entity_name(entity)
        if zone is None or zone.zone_index is None:
            logger.error(f"Unable to find zone for entity: {entity}")
            return
        cmd_string = f"A=1 Z={zone.zone_index} SP={setpoint:.0f}"
        with self.conn_lock:
            sleep(self.SLEEP_BETWEEN_COMMS)
            self.conn.write(cmd_string.encode("utf-8"))
        logger.debug(f"Sent command: {cmd_string}")
        if zone.current_setpoint != setpoint:
            zone.modified_since_last_sync = True
            zone.current_setpoint = setpoint

    def set_mode(self, entity: str, mode: str):
        if not self.conn or not self.conn.is_open or mode not in self.MODE_MAP_MQTT2RCS:
            logger.error("Bad call to set_mode().")
            return
        zone = zones.get_zone_by_entity_name(entity)
        if zone is None or zone.zone_index is None:
            logger.error(f"Unable to find zone for entity: {entity}")
            return
        rcs_mode = self.MODE_MAP_MQTT2RCS[mode]
        if rcs_mode is not None:
            cmd_string = f"A=1 Z={zone.zone_index} M={mode}"
        else:
            return
        with self.conn_lock:
            sleep(self.SLEEP_BETWEEN_COMMS)
            self.conn.write(cmd_string.encode("utf-8"))
        logger.debug(f"Sent command: {cmd_string}")
        if zone.current_mode != mode:
            zone.current_mode = mode
            zone.modified_since_last_sync = True

    def _get_all_zone_status(self) -> bool:
        if not self.conn:
            logger.error("RCSController not connected")
            return False
        with self.conn_lock:
            sleep(self.SLEEP_BETWEEN_COMMS)
            self.conn.write(b"A=1 R=1\r")
            status_type_1 = self.conn.read_until(b"\r")
            sleep(self.SLEEP_BETWEEN_COMMS)
            self.conn.write(b"A=1 R=2\r")
            status_type_2 = self.conn.read_until(b"\r")
        self._process_status_type_1(status_type_1)
        self._process_status_type_2(status_type_2)
        return True

    # noinspection PyMethodMayBeStatic
    def _process_status_type_1(self, status_type_1: bytes):
        zone: zones.Zone | None = None
        param_list_1 = status_type_1.split()
        for param in param_list_1:
            match param:
                case param if param.startswith(self.ZONE_ID_PREFIX):
                    zone_index = int(param[len(self.ZONE_ID_PREFIX) :])
                    logger.debug(f"Zone index: {zone_index}")
                    zone = zones.get_zone_by_index(zone_index)
                    if zone is None:
                        logger.error(f"Bad zone {param}")

                case param if param.startswith(b"self.TEMP_PREFIX"):
                    if zone is None:
                        break
                    try:
                        temperature = float(param[len("self.TEMP_PREFIX") :])
                    except ValueError:
                        logger.error(f"Bad temperature: {param}")
                        return False
                    logger.debug(f"Temperature: {temperature}")
                    if zone.current_temperature != temperature:
                        zone.current_temperature = temperature
                        zone.modified_since_last_sync = True

                case param if param.startswith(self.SETPOINT_PREFIX):
                    if zone is None:
                        break
                    try:
                        setpoint = float(param[len(self.SETPOINT_PREFIX) :])
                    except ValueError:
                        logger.error(f"Bad setpoint {param}")
                        return False
                    logger.debug(f"Setpoint: {setpoint}")
                    if zone.current_setpoint != setpoint:
                        zone.current_setpoint = setpoint
                        zone.modified_since_last_sync = True

                case param if param.startswith(self.MODE_PREFIX):
                    if zone is None:
                        break
                    mode = param[len(self.MODE_PREFIX) :].decode("ascii")
                    if mode not in self.MODE_MAP_RCS2MQTT:
                        logger.error(f"Bad mode: {param}")
                        break
                    logger.debug(f"Mode: {mode}")
                    if zone.current_mode != mode:
                        zone.current_mode = mode
                        zone.modified_since_last_sync = True

                case param if param.startswith(self.FAN_MODE_PREFIX):
                    if zone is None:
                        break
                    fan_mode = param[len("FM=") :].decode("ascii")
                    logger.debug(f"Fan mode: {fan_mode}. Not used.")

                case _:
                    logger.debug(f"Ignored Type 1 parameter: {param}")

    # noinspection PyMethodMayBeStatic
    def _process_status_type_2(self, status_type_2: bytes):
        is_hvac_heating: bool | None = None
        param_list_2 = status_type_2.split()
        for param in param_list_2:
            match param:
                case param if param.startswith(self.HEAT_CALL_PREFIX):
                    heat_call = int(param[len(self.HEAT_CALL_PREFIX) :])
                    if heat_call not in [0, 1]:
                        logger.error(f"Bad heat call: {param}")
                        break
                    logger.debug(f"Heat call: {heat_call}")
                    is_hvac_heating = heat_call == 1

                case param if param.startswith(self.DAMPER_STATUS_PREFIX):
                    if is_hvac_heating is None:
                        logger.error("Missing heat status data before damper status.")
                        break
                    zone_index = int(param[1:2])
                    zone = zones.get_zone_by_index(zone_index)
                    if zone is None:
                        logger.error(f"Bad zone in Type 2 damper message: {param}")
                        break
                    damper_status = int(param[3:])
                    if damper_status not in [0, 1]:
                        logger.error(
                            f"Bad damper status in Type 2 damper message: {param}"
                        )
                        break

                    is_damper_open = damper_status == 0
                    is_zone_heating = is_damper_open and is_hvac_heating
                    if zone.is_heating != is_zone_heating:
                        zone.is_heating = is_zone_heating
                        zone.modified_since_last_sync = True
                    if zone.is_damper_open != is_damper_open:
                        zone.is_damper_open = is_damper_open
                        zone.modified_since_last_sync = True
                    if zone.current_mode == "off":
                        current_action = "off"
                        if is_zone_heating:
                            logger.error(
                                f"Zone {zone.entity_name} heating when off. WTF."
                            )
                            break
                    else:
                        current_action = "heating" if is_zone_heating else "idle"
                    if zone.current_action != current_action:
                        zone.current_action = current_action
                        zone.modified_since_last_sync = True

                case _:
                    logger.debug(f"Ignored Type 2 parameter: {param}")

        return True

    def force_sync(self) -> None:
        self.first_pass = True
