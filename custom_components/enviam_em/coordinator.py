import logging
from datetime import datetime, timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ANALYTICS_SCAN_INTERVAL_SECONDS,
    DATA_ANALYTICS_COORDINATOR,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
)
from .api import EnviamAPI, EnviamAuthError, EnviamConnectionError
from homeassistant.exceptions import ConfigEntryAuthFailed

_LOGGER = logging.getLogger(__name__)


class EnviamDataCoordinator(DataUpdateCoordinator):
    """Coordinator for the live energy-flow endpoint."""

    def __init__(self, hass, api: EnviamAPI, config_entry=None):
        _LOGGER.debug("Coordinator wird erstellt: domain=%s, interval=%ss", DOMAIN, SCAN_INTERVAL_SECONDS)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    async def _async_update_data(self):
        _LOGGER.debug("Coordinator-Update gestartet")
        try:
            data = await self.api.async_get_energy_data()
            _LOGGER.debug(
                "Coordinator-Update erfolgreich: top_level_keys=%s",
                list(data) if isinstance(data, dict) else type(data).__name__,
            )
            return data
        except EnviamAuthError as err:
            _LOGGER.warning("Coordinator-Update Auth-Fehler: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except EnviamConnectionError as err:
            _LOGGER.warning("Coordinator-Update Verbindungsfehler: %s", err)
            raise UpdateFailed(f"Verbindung zur enviaM-API fehlgeschlagen: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unerwarteter Fehler beim Coordinator-Update: %s", err)
            raise UpdateFailed(f"Fehler beim Abrufen der Daten: {err}")


class EnviamAnalyticsCoordinator(DataUpdateCoordinator):
    """Coordinator for the daily work (energy) analytics endpoint."""

    def __init__(self, hass, api: EnviamAPI, config_entry=None):
        _LOGGER.debug(
            "Analytics-Coordinator wird erstellt: domain=%s, interval=%ss",
            DOMAIN,
            ANALYTICS_SCAN_INTERVAL_SECONDS,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{DATA_ANALYTICS_COORDINATOR}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=ANALYTICS_SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    @staticmethod
    def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
        """Return local midnight and the last second of the current day."""
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        return start, end

    async def _async_update_data(self):
        _LOGGER.debug("Analytics-Coordinator-Update gestartet")
        start, end = self._day_bounds(dt_util.now())
        try:
            data = await self.api.async_get_analytics_overview(start, end)
            _LOGGER.debug(
                "Analytics-Coordinator-Update erfolgreich: top_level_keys=%s",
                list(data) if isinstance(data, dict) else type(data).__name__,
            )
            return data
        except EnviamAuthError as err:
            _LOGGER.warning("Analytics-Coordinator-Update Auth-Fehler: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except EnviamConnectionError as err:
            _LOGGER.warning("Analytics-Coordinator-Update Verbindungsfehler: %s", err)
            raise UpdateFailed(f"Verbindung zur enviaM-API fehlgeschlagen: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unerwarteter Fehler beim Analytics-Coordinator-Update: %s", err)
            raise UpdateFailed(f"Fehler beim Abrufen der Verbrauchsdaten: {err}")
