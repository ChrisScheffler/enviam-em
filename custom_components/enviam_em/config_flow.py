import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnviamAPI, EnviamAuthError, EnviamConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EnviamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        """Store the config entry being re-authenticated, if any."""
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input=None):
        errors = {}
        _LOGGER.debug("Config-Flow-Schritt user gestartet; Eingabe vorhanden=%s", user_input is not None)

        if user_input is not None:
            username = user_input["username"].strip()
            password = user_input["password"]
            _LOGGER.debug("Config-Flow: Anmeldeversuch gestartet; username_present=%s", bool(username))

            if not username or not password:
                errors["base"] = "invalid_auth"
            else:
                await self.async_set_unique_id(username.casefold())
                self._abort_if_unique_id_configured()

                session = async_get_clientsession(self.hass)
                api = EnviamAPI(username, password, session)

                try:
                    success = await api.async_login()
                except EnviamAuthError:
                    _LOGGER.debug("Config-Flow: Authentifizierung fehlgeschlagen")
                    errors["base"] = "invalid_auth"
                except EnviamConnectionError:
                    _LOGGER.debug("Config-Flow: Verbindung fehlgeschlagen")
                    errors["base"] = "cannot_connect"
                except (TimeoutError, OSError):
                    _LOGGER.debug("Config-Flow: Netzwerkfehler während Authentifizierung")
                    errors["base"] = "cannot_connect"
                else:
                    if success:
                        _LOGGER.debug("Config-Flow: Einrichtung erfolgreich")
                        return self.async_create_entry(
                            title=username, data={"username": username, "password": password}
                        )

                    errors["base"] = "invalid_auth"
                    _LOGGER.debug("Config-Flow: API meldete erfolglose Einrichtung")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, user_input=None):
        """Handle a failed authentication by asking for new credentials."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Confirm re-authentication with a new password."""
        errors = {}
        entry = self._reauth_entry

        if user_input is not None and entry is not None:
            password = user_input["password"]
            username = entry.data["username"]
            _LOGGER.debug("Reauth-Flow: Anmeldeversuch gestartet")

            if not password:
                errors["base"] = "invalid_auth"
            else:
                session = async_get_clientsession(self.hass)
                api = EnviamAPI(username, password, session)

                try:
                    success = await api.async_login()
                except EnviamAuthError:
                    _LOGGER.debug("Reauth-Flow: Authentifizierung fehlgeschlagen")
                    errors["base"] = "invalid_auth"
                except EnviamConnectionError:
                    _LOGGER.debug("Reauth-Flow: Verbindung fehlgeschlagen")
                    errors["base"] = "cannot_connect"
                except (TimeoutError, OSError):
                    _LOGGER.debug("Reauth-Flow: Netzwerkfehler während Authentifizierung")
                    errors["base"] = "cannot_connect"
                else:
                    if success:
                        _LOGGER.debug("Reauth-Flow: Anmeldung erfolgreich; Entry wird aktualisiert")
                        self.hass.config_entries.async_update_entry(
                            entry, data={**entry.data, "password": password}
                        )
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        return self.async_abort(reason="reauth_successful")

                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
            description_placeholders={"username": entry.data["username"] if entry else ""},
        )
