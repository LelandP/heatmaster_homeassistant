"""Platform for sensor integration."""
from __future__ import annotations

import logging
from cachetools import cached, TTLCache
from homeassistant.util import Throttle

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import Entity
from homeassistant.const import TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .heatmasterajax import HeatmasterAjax

_LOGGER = logging.getLogger(__name__)

DOMAIN="heatmaster_hassio"
#name, key name, Device Class, state_class
SENSOR_LIST = [["Water Temperature", "Temperature", SensorDeviceClass.TEMPERATURE, TEMP_FAHRENHEIT],
               ["O2", "o2", "oxygen", "%"],
               ["Top Damper", "Top Damper", "damper_pos", "%"],
               ["Bottom Damper", "Bot Damper", "damper_pos", "%"],
               ["Furnace Status", "Status", None, None]]

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    hm_data = HeatmasterData(HeatmasterAjax(config["ip"]))
    sensors = [HeatMasterSensor(hm_data, data[0], data[1], data[2], data[3]) for data in SENSOR_LIST]
    add_entities(sensors)

class HeatMasterSensor(SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, heatmaster_data, name, value_key, device_class, unit_of_mesurement):
        super().__init__()
        self._name = f"{DOMAIN} {name}"
        self._value_key = value_key
        self._unique_id = f"{self._name.lower()}-{self._value_key.replace(' ', '_').lower()}"
        self._value = None
        self._available = True
        self.hm = heatmaster_data
        self.data = None
        
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_mesurement

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._unique_id)
            },
            name="Heatmaster",
            manufacturer="Heatmaster",
            model="LOGO8",
            sw_version="1.0.0",
            via_device=(DOMAIN, "Heatmaster")
        )

    def update(self) -> None:
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        self.hm.update()
        self._value = self.hm.data[self._value_key]

class HeatmasterData:
    def __init__(self, heatmaster_ajax):
        self.heatmaster_ajax = heatmaster_ajax
        self.data = None

    @cached(cache=TTLCache(maxsize=10, ttl=5))
    def update(self):
        self.data = self.heatmaster_ajax.get_data()