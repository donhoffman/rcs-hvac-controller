import logging
from typing import TypeAlias, Dict

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
logger = logging.getLogger("app.zones")


class Zone(object):
    def __init__(
        self,
        name: str,
        zone_index: int,
    ):
        self.name = name
        self.zone_index = zone_index
        self.entity_name = f"zone_{zone_index}"

        self.current_temperature: float | None = None
        self.current_setpoint: float | None = None
        self.current_mode: str | None = None
        self.current_action: str | None = None
        self.is_heating: bool = False
        self.is_damper_open: bool = False
        self.modified_since_last_sync: bool = False


zones_by_index: Dict[int, Zone] = {}
zones_by_entity: Dict[str, Zone] = {}


def create_zones_from_config(
    zone_config: JSON | list["JSON"] | str | int | float | bool | None,
) -> bool:
    zones = zone_config.get("zones")
    if (zones is None) or not isinstance(zones, list) or not (len(zones) >= 1):
        logger.error("No zones specified.")
        return False
    for zone in zones:
        if zone.get("name") is None or zone.get("index") is None:
            logger.error("One of zone 'name', or 'index' missing.")
            return False
        new_zone = Zone(
            name=zone.get("name"),
            zone_index=zone.get("index"),
        )
        zones_by_index[new_zone.zone_index] = new_zone
        zones_by_entity[new_zone.entity_name] = new_zone
    return True


def get_zone_by_index(index: int) -> Zone | None:
    return zones_by_index.get(index)


def get_zone_by_entity_name(entity_name: str) -> Zone | None:
    return zones_by_entity.get(entity_name)
