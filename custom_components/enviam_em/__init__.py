import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DATA_ANALYTICS_COORDINATOR, DATA_ENERGY_COORDINATOR, DOMAIN
from .api import EnviamAPI, EnviamAuthError, EnviamConnectionError
from .coordinator import EnviamAnalyticsCoordinator, EnviamDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Setup gestartet: entry_id=%s", entry.entry_id)
    session = async_get_clientsession(hass)
    api = EnviamAPI(entry.data["username"], entry.data["password"], session)

    try:
        if not await api.async_login():
            raise ConfigEntryAuthFailed("Login bei Enviam fehlgeschlagen.")
    except EnviamAuthError as err:
        _LOGGER.debug("Setup wegen Authentifizierungsfehler abgebrochen: %s", err)
        raise ConfigEntryAuthFailed(str(err)) from err
    except EnviamConnectionError as err:
        _LOGGER.debug("Setup wegen Verbindungsfehler abgebrochen: %s", err)
        raise ConfigEntryNotReady(str(err)) from err

    _LOGGER.debug("Authentifizierung erfolgreich; erster Coordinator-Refresh startet")
    coordinator = EnviamDataCoordinator(hass, api, config_entry=entry)
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug("Erster Analytics-Coordinator-Refresh startet")
    analytics_coordinator = EnviamAnalyticsCoordinator(hass, api, config_entry=entry)
    await analytics_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_ENERGY_COORDINATOR: coordinator,
        DATA_ANALYTICS_COORDINATOR: analytics_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _LOGGER.debug("Setup abgeschlossen: Sensor-Plattform weitergeleitet")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unload gestartet: entry_id=%s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        _LOGGER.debug("Unload erfolgreich: entry_id=%s", entry.entry_id)
    else:
        _LOGGER.debug("Unload fehlgeschlagen: entry_id=%s", entry.entry_id)
    return unload_ok
