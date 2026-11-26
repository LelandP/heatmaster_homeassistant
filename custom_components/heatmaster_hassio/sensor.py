"""Platform for sensor integration."""
from __future__ import annotations

import logging

from cachetools import TTLCache, cached
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .heatmasterajax import HeatmasterAjax

_LOGGER = logging.getLogger(__name__)

DOMAIN="heatmaster_hassio"
#name, key name, Device Class, state_class
SENSOR_LIST = [["Water Temperature", "Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.FAHRENHEIT],
               ["O2", "o2", "oxygen", "%"],
               # This can be the text "MaxAir" during Cold Start, not only a percentage.
               ["Top Damper", "Top Damper", None, None],
               ["Bottom Damper", "Bot Damper", "damper_pos", "%"],
               ["Furnace Status", "Status", "status", None],
               ["Boiler Alarm", "Alarm", None, None],
               ["Boiler Bypass", "Bypass", None, None]]

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
    """Representation of a Sensor configured via legacy YAML."""

    def __init__(self, heatmaster_data, name, value_key, device_class, unit_of_mesurement):
        super().__init__()
        self._name = f"{DOMAIN} {name}"
        self._value_key = value_key
        self._unique_id = f"{self._name.lower()}-{self._value_key.replace(' ', '_').lower()}"
        self._value = None
        self._available = True
        self.hm = heatmaster_data
        self.data = None
        
        # self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = device_class
        if unit_of_mesurement is not None:
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
    def native_unit_of_measurement(self) -> str | None:
        """Show percent for numeric damper readings, but not for MaxAir text."""
        if self._value_key == "Top Damper":
            return "%" if isinstance(self._value, (int, float)) else None
        return getattr(self, "_attr_native_unit_of_measurement", None)

    def update(self) -> None:
        """Fetch the shared poll result and mark unavailable values appropriately."""
        self.hm.update()
        data = self.hm.data
        if not data:
            self._available = False
            self._value = None
            _LOGGER.warning("No Heatmaster data available for %s", self._value_key)
            return

        self._available = True
        self._value = data.get(self._value_key)

class HeatmasterData:
    def __init__(self, heatmaster_ajax):
        self.heatmaster_ajax = heatmaster_ajax
        self.data = None

    @cached(cache=TTLCache(maxsize=10, ttl=5))
    def update(self):
        self.data = self.heatmaster_ajax.get_data()
        _LOGGER.debug(f"Raw Data from HeatMasterClass: {self.data}")
