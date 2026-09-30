import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DATA_ANALYTICS_COORDINATOR,
    DATA_ENERGY_COORDINATOR,
    DEVICE_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    UNIT_KILO_WATT_HOUR,
    UNIT_WATT_HOUR,
)

_LOGGER = logging.getLogger(__name__)

# Umrechnungsfaktoren der von der Analytics-API gelieferten Einheiten nach kWh.
_UNIT_TO_KWH = {
    UNIT_WATT_HOUR: 0.001,
    UNIT_KILO_WATT_HOUR: 1.0,
}

# Definition der Sensoren basierend auf der JSON-Struktur
SENSOR_TYPES = {
    "pv_power": {
        "name": "PV Production",
        "value_fn": lambda data: data.get("pv", {}).get("out", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "grid_power": {
        "name": "Grid Import",
        "value_fn": lambda data: data.get("grid", {}).get("in", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "grid_export": {
        "name": "Grid Export",
        "value_fn": lambda data: data.get("grid", {}).get("out", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "consumption_power": {
        "name": "Home Consumption",
        "value_fn": lambda data: data.get("consumption", {}).get("in", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "ev_power": {
        "name": "EV Charging",
        "value_fn": lambda data: data.get("ev", {}).get("in", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "ev_export": {
        "name": "EV Discharging",
        "value_fn": lambda data: data.get("ev", {}).get("out", 0),
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
}

# Sensoren für die Arbeit (Energie) des aktuellen Tages. Die Werte werden aus der
# Timeseries der Anlage (nicht der Einzelgeräte) gelesen und in kWh umgerechnet.
# Da die API je nach Anlagenkonfiguration unterschiedliche Seriennamen liefert,
# werden mehrere Kandidaten geprüft; fehlende Werte werden abgeleitet.
ANALYTICS_SENSOR_TYPES = {
    "energy_consumed": {
        "name": "Energy Consumed Today",
        "series": ("WorkConsumed",),
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    "energy_from_grid": {
        "name": "Energy From Grid Today",
        "series": ("WorkIn", "WorkGridIn", "WorkConsumedFromGrid"),
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    "energy_self_consumed": {
        "name": "Energy Self Consumed Today",
        "series": ("WorkConsumedFromProducers", "WorkSelfConsumed"),
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    "energy_produced": {
        "name": "Energy Produced Today",
        "series": ("WorkProduced", "WorkProduction", "WorkGenerated"),
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    "energy_to_grid": {
        "name": "Energy To Grid Today",
        "series": ("WorkOut", "WorkGridOut", "WorkFeedIn"),
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    # Abgeleitete Kennzahlen; sie werden aus den Serien oben berechnet und
    # benötigen daher selbst keine "series"-Zuordnung.
    "self_sufficiency_ratio": {
        "name": "Self Sufficiency Today",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
    },
    "self_consumption_ratio": {
        "name": "Self Consumption Ratio Today",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
    },
}


def _root_guid(data: dict) -> str | None:
    """Return the guid of the plant itself, ignoring single devices."""
    timeseries = data.get("timeseries")
    if not isinstance(timeseries, list):
        return None
    device_ids = {
        device.get("id")
        for device in data.get("devices") or []
        if isinstance(device, dict) and device.get("id")
    }
    plant_guid = None
    fallback = None
    for entry in timeseries:
        if not isinstance(entry, dict):
            continue
        guid = entry.get("guid")
        if not isinstance(guid, str) or not guid:
            continue
        if guid in device_ids:
            continue
        if fallback is None:
            fallback = guid
        # WorkConsumed existiert nur für die Anlage, nicht für Einzelgeräte.
        if plant_guid is None and entry.get("name") == "WorkConsumed":
            plant_guid = guid
    return plant_guid or fallback


def _plant_series(data: dict) -> dict[str, dict]:
    """Return the plant timeseries entries keyed by their series name."""
    timeseries = data.get("timeseries")
    if not isinstance(timeseries, list):
        return {}
    guid = _root_guid(data)
    series: dict[str, dict] = {}
    for entry in timeseries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        if guid is not None and entry.get("guid") != guid:
            continue
        # Die Anlagenserie hat Vorrang vor einem gleichnamigen Gerätewert.
        series.setdefault(name, entry)
    return series


def _to_kwh(value, unit: str | None) -> float | None:
    """Convert a work value reported by the API into kWh."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    factor = _UNIT_TO_KWH.get(unit, _UNIT_TO_KWH[UNIT_WATT_HOUR])
    return numeric * factor


def _first_present(values: dict[str, float], names: tuple[str, ...]) -> float | None:
    """Return the first value available under one of the candidate names."""
    for name in names:
        if values.get(name) is not None:
            return values[name]
    return None


def _analytics_values(data: dict) -> dict[str, float]:
    """Resolve the aggregated plant values (kWh) for every analytics sensor."""
    series = _plant_series(data)
    aggregated = {
        name: _to_kwh(entry.get("aggregated"), entry.get("unit"))
        for name, entry in series.items()
    }

    values: dict[str, float] = {}
    for sensor_key, sensor_info in ANALYTICS_SENSOR_TYPES.items():
        # Abgeleitete Kennzahlen haben keine eigene Serie.
        series_names = sensor_info.get("series")
        if not series_names:
            continue
        value = _first_present(aggregated, series_names)
        if value is not None:
            values[sensor_key] = value

    # Erzeugung und Einspeisung fehlen je nach Anlage; beide lassen sich
    # auseinander bzw. aus dem Eigenverbrauch ableiten.
    produced = values.get("energy_produced")
    self_consumed = values.get("energy_self_consumed")
    to_grid = values.get("energy_to_grid")

    if produced is None and self_consumed is not None and to_grid is not None:
        produced = self_consumed + to_grid
        values["energy_produced"] = produced
    if to_grid is None and produced is not None and self_consumed is not None:
        to_grid = max(produced - self_consumed, 0.0)
        values["energy_to_grid"] = to_grid

    # Autarkiegrad: Anteil des Verbrauchs, der ohne Netzbezug gedeckt wurde.
    consumed = values.get("energy_consumed")
    if consumed and self_consumed is not None:
        values["self_sufficiency_ratio"] = round(max(min(self_consumed / consumed, 1.0), 0.0) * 100, 1)

    # Eigenverbrauchsanteil: Anteil der Erzeugung, der selbst verbraucht wurde.
    if produced and self_consumed is not None:
        values["self_consumption_ratio"] = round(max(min(self_consumed / produced, 1.0), 0.0) * 100, 1)

    _LOGGER.debug("Analytics-Werte aufgelöst: %s", values)
    return values


def _hourly_values(entry: dict | None) -> dict[str, float]:
    """Return the per-interval values of a series in kWh, keyed by local hour."""
    if not isinstance(entry, dict):
        return {}
    raw_values = entry.get("values")
    if not isinstance(raw_values, dict):
        return {}
    unit = entry.get("unit")
    hourly: dict[str, float] = {}
    for timestamp, value in raw_values.items():
        if not isinstance(timestamp, str) or len(timestamp) < 13:
            continue
        converted = _to_kwh(value, unit)
        if converted is None:
            continue
        hourly[timestamp[:13]] = round(converted, 3)
    return dict(sorted(hourly.items()))


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the enviaM energy sensors."""
    _LOGGER.debug("Sensor-Setup gestartet: entry_id=%s", entry.entry_id)
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not isinstance(entry_data, dict):
        _LOGGER.error("Kein Datenkoordinator für Config Entry %s vorhanden", entry.entry_id)
        return

    coordinator = entry_data.get(DATA_ENERGY_COORDINATOR)
    analytics_coordinator = entry_data.get(DATA_ANALYTICS_COORDINATOR)

    entities = []
    if coordinator is not None:
        for sensor_key, sensor_info in SENSOR_TYPES.items():
            _LOGGER.debug("Sensor-Entity wird erstellt: key=%s, name=%s", sensor_key, sensor_info["name"])
            entities.append(EnviamEnergySensor(coordinator, entry, sensor_key, sensor_info))
    else:
        _LOGGER.error("Kein Energy-Flow-Koordinator für Config Entry %s vorhanden", entry.entry_id)

    if analytics_coordinator is not None:
        for sensor_key, sensor_info in ANALYTICS_SENSOR_TYPES.items():
            _LOGGER.debug(
                "Analytics-Sensor-Entity wird erstellt: key=%s, name=%s",
                sensor_key,
                sensor_info["name"],
            )
            entities.append(
                EnviamAnalyticsSensor(analytics_coordinator, entry, sensor_key, sensor_info)
            )
    else:
        _LOGGER.error("Kein Analytics-Koordinator für Config Entry %s vorhanden", entry.entry_id)

    async_add_entities(entities)
    _LOGGER.debug("Sensor-Setup abgeschlossen: entity_count=%s", len(entities))


class EnviamEnergySensor(CoordinatorEntity, SensorEntity):
    """Representation of an enviaM Energy Sensor."""

    def __init__(self, coordinator, entry, sensor_key, sensor_info):
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_has_entity_name = True
        self._attr_name = sensor_info["name"]
        self._attr_device_class = sensor_info["device_class"]
        self._attr_state_class = sensor_info["state_class"]
        self._attr_native_unit_of_measurement = sensor_info["unit"]
        self._attr_suggested_display_precision = 0

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": DEVICE_NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        data = self.coordinator.data
        if not data:
            return None

        try:
            value = self._sensor_info["value_fn"](data)
            parsed_value = float(value) if value is not None else None
            _LOGGER.debug("Sensorwert gelesen: key=%s, value=%s", self._sensor_key, parsed_value)
            return parsed_value
        except (AttributeError, TypeError, ValueError):
            _LOGGER.warning("Could not parse value for %s", self._sensor_key)
            return None

    @property
    def available(self) -> bool:
        """Return whether the coordinator has usable data."""
        return super().available and isinstance(self.coordinator.data, dict)

    @property
    def extra_state_attributes(self):
        """Füge Geräte-IDs als Attribute hinzu, falls für Automatisierungen benötigt."""
        data = self.coordinator.data
        if not data:
            return {}

        # Extrahiere die Geräte-IDs aus dem entsprechenden Abschnitt
        section_key = self._sensor_key.split("_")[0]  # z.B. "pv" aus "pv_power"
        section = data.get(section_key)
        if not isinstance(section, dict):
            return {}
        devices = section.get("devices", [])
        if not isinstance(devices, list):
            return {}
        attributes = {
            "device_ids": [d.get("id") for d in devices if isinstance(d, dict) and d.get("id")]
        }
        _LOGGER.debug(
            "Sensorattribute gelesen: key=%s, device_count=%s",
            self._sensor_key,
            len(attributes["device_ids"]),
        )
        return attributes


class EnviamAnalyticsSensor(CoordinatorEntity, SensorEntity):
    """Representation of a daily work (energy) sensor of the enviaM plant."""

    def __init__(self, coordinator, entry, sensor_key, sensor_info):
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_has_entity_name = True
        self._attr_name = sensor_info["name"]
        self._attr_device_class = sensor_info["device_class"]
        self._attr_state_class = sensor_info["state_class"]
        self._attr_native_unit_of_measurement = sensor_info["unit"]
        self._attr_suggested_display_precision = 2

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": DEVICE_NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def native_value(self):
        """Return the aggregated work of the current day in kWh."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        try:
            value = _analytics_values(data).get(self._sensor_key)
            _LOGGER.debug("Analytics-Sensorwert gelesen: key=%s, value=%s", self._sensor_key, value)
            return value
        except (AttributeError, TypeError, ValueError):
            _LOGGER.warning("Could not parse value for %s", self._sensor_key)
            return None

    @property
    def available(self) -> bool:
        """Return whether the coordinator delivered usable analytics data."""
        if not super().available or not isinstance(self.coordinator.data, dict):
            return False
        return self._sensor_key in _analytics_values(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        """Expose the per-interval values and the API metadata."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return {}

        series = _plant_series(data)
        entry = None
        for name in self._sensor_info.get("series") or ():
            if name in series:
                entry = series[name]
                break

        attributes: dict[str, object] = {
            "resolution": data.get("resolution"),
            "time_zone": data.get("time_zone"),
            "source_series": entry.get("name") if isinstance(entry, dict) else None,
            "source_unit": entry.get("unit") if isinstance(entry, dict) else None,
            "hourly": _hourly_values(entry),
        }
        return attributes
