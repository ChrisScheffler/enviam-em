import base64
import binascii
import json
import logging
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup

from .const import (
    CONTEXT_URL,
    DEFAULT_TARGET_URL,
    ENERGY_FLOW_URL,
    OVERVIEW_HOST,
    ANALYTICS_OVERVIEW_URL,
    ANALYTICS_TYPE,
)

_LOGGER = logging.getLogger(__name__)
TOKEN_REFRESH_BUFFER_SECONDS = 30


class EnviamAuthError(Exception):
    """Authentication failed or the authenticated context is invalid."""


class EnviamConnectionError(Exception):
    """The enviaM service could not be reached."""


def _extract_jwt_exp(token: str) -> float | None:
    """Return the JWT expiration timestamp without validating the signature."""
    if not isinstance(token, str) or len(token.split(".")) != 3:
        return None
    try:
        payload_part = token.split(".", 2)[1]
        payload = json.loads(
            base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        )
        expiration = payload.get("exp")
        return float(expiration) if expiration is not None else None
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


class EnviamAPI:
    def __init__(self, username: str, password: str, session: ClientSession):
        self.username = username
        self.password = password
        self.session = session
        self._access_token: str | None = None
        self._refresh_token_path: str | None = None
        self._token_expires_at: float | None = None

    @staticmethod
    def _is_overview_response(response, page: str) -> bool:
        """Return whether the final response is the authenticated overview page."""
        if response.url.host != OVERVIEW_HOST:
            return False
        if response.url.path.rstrip("/") != "/overview":
            return False
        return BeautifulSoup(page, "html.parser").find("form") is None

    async def async_login(self) -> bool:
        """Authenticate through overview/Keycloak and initialize the context token."""
        _LOGGER.debug("Login gestartet: GET %s", DEFAULT_TARGET_URL)
        try:
            async with self.session.get(DEFAULT_TARGET_URL) as response:
                response.raise_for_status()
                page = await response.text()
                final_url = response.url
                _LOGGER.debug(
                    "Overview-Antwort: status=%s, final_url=%s://%s%s",
                    response.status,
                    final_url.scheme,
                    final_url.host,
                    final_url.path,
                )

            if final_url.host == OVERVIEW_HOST:
                _LOGGER.debug("Bestehende Session erkannt; kein Keycloak-Formular erforderlich")
                if not self._is_overview_response(response, page):
                    raise EnviamAuthError("Die enviaM-Sitzung wurde nicht authentifiziert.")
            else:
                soup = BeautifulSoup(page, "html.parser")
                form = soup.find("form")
                if form is None or not form.get("action"):
                    raise EnviamAuthError("Die enviaM-Anmeldeseite enthält kein Login-Formular.")
                _LOGGER.debug("Keycloak-Loginformular erkannt; Credentials werden übertragen")
                form_data = {
                    field["name"]: field.get("value", "")
                    for field in form.find_all("input")
                    if field.get("name")
                }
                form_data.update({"username": self.username, "password": self.password})
                async with self.session.post(
                    urljoin(str(final_url), form["action"]),
                    data=form_data,
                    allow_redirects=True,
                ) as login_response:
                    login_response.raise_for_status()
                    page = await login_response.text()
                    _LOGGER.debug(
                        "Keycloak-Loginantwort: status=%s, final_url=%s://%s%s",
                        login_response.status,
                        login_response.url.scheme,
                        login_response.url.host,
                        login_response.url.path,
                    )
                    if not self._is_overview_response(login_response, page):
                        raise EnviamAuthError("Die enviaM-Anmeldedaten wurden abgelehnt.")

            _LOGGER.debug("Overview erfolgreich; Context wird abgerufen: %s", CONTEXT_URL)
            if not await self._async_fetch_context():
                raise EnviamAuthError("Die enviaM-Context-Antwort enthält keinen Access-Token.")
            _LOGGER.debug("Login abgeschlossen; Access-Token und Refresh-Pfad initialisiert")
            return True
        except EnviamAuthError:
            _LOGGER.debug("Login mit Authentifizierungsfehler abgebrochen")
            raise
        except (ClientError, TimeoutError) as err:
            _LOGGER.debug("Login wegen Verbindungsfehler abgebrochen: %s", err)
            raise EnviamConnectionError(str(err)) from err

    async def _async_fetch_context(self) -> bool:
        """Fetch the OAuth data using the cookies from the overview request."""
        _LOGGER.debug("Context-Request gestartet: GET %s", CONTEXT_URL)
        try:
            async with self.session.get(CONTEXT_URL) as response:
                _LOGGER.debug("Context-Antwort: status=%s", response.status)
                if response.status in (401, 403):
                    raise EnviamAuthError("Die enviaM-Sitzung ist nicht authentifiziert.")
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except EnviamAuthError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise EnviamConnectionError(f"Context konnte nicht gelesen werden: {err}") from err

        if not isinstance(payload, dict):
            _LOGGER.debug("Context-Antwort ist kein JSON-Objekt")
            return False
        oauth = payload.get("oauth")
        if not isinstance(oauth, dict):
            _LOGGER.debug("Context-JSON enthält keinen oauth-Abschnitt; keys=%s", list(payload))
            return False
        access_token = oauth.get("accessToken")
        refresh_token_path = oauth.get("refreshTokenPath")
        if not isinstance(access_token, str) or not access_token:
            _LOGGER.debug("Context-JSON enthält keinen accessToken")
            return False
        if not isinstance(refresh_token_path, str) or not refresh_token_path:
            _LOGGER.debug("Context-JSON enthält keinen refreshTokenPath")
            return False
        self._access_token = access_token
        self._refresh_token_path = refresh_token_path
        self._token_expires_at = _extract_jwt_exp(access_token)
        _LOGGER.debug(
            "Context verarbeitet: accessToken vorhanden, refreshTokenPath=%s, expires_at=%s",
            refresh_token_path,
            self._token_expires_at,
        )
        return True

    async def _async_refresh_token(self) -> bool:
        """Refresh the access token through the path supplied by context."""
        if not self._refresh_token_path:
            _LOGGER.debug("Token-Refresh übersprungen: kein refreshTokenPath vorhanden")
            return False
        try:
            # refreshTokenPath kommt als Root-Pfad, z. B.
            # /rest/auth/refreshAccessToken. Der Context-Pfad darf nicht
            # Bestandteil der Refresh-URL werden.
            refresh_path = f"/{self._refresh_token_path.lstrip('/')}"
            context_parts = urlsplit(CONTEXT_URL)
            refresh_url = urlunsplit(
                (context_parts.scheme, context_parts.netloc, refresh_path, "", "")
            )
            headers = {"Authorization": f"Bearer {self._access_token}"} if self._access_token else {}
            _LOGGER.debug("Token-Refresh gestartet: GET %s", refresh_url)
            async with self.session.get(refresh_url, headers=headers) as response:
                _LOGGER.debug("Token-Refresh-Antwort: status=%s", response.status)
                if response.status in (401, 403):
                    return False
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Token-Refresh fehlgeschlagen: %s", err)
            return False

        if not isinstance(payload, dict):
            _LOGGER.debug("Token-Refresh-Antwort ist kein JSON-Objekt")
            return False
        access_token = payload.get("accessToken") or payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            _LOGGER.debug("Token-Refresh-Antwort enthält keinen accessToken")
            return False
        self._access_token = access_token
        self._token_expires_at = _extract_jwt_exp(access_token)
        _LOGGER.debug("Token-Refresh erfolgreich; neue expires_at=%s", self._token_expires_at)
        return True

    async def _async_ensure_valid_token(self) -> bool:
        if not self._access_token:
            _LOGGER.debug("Kein Access-Token vorhanden; vollständiger Login erforderlich")
            return await self.async_login()
        if self._token_expires_at is not None and time.time() >= (
            self._token_expires_at - TOKEN_REFRESH_BUFFER_SECONDS
        ):
            _LOGGER.debug("Access-Token läuft innerhalb des Refresh-Puffers ab")
            if await self._async_refresh_token():
                return True
            # Refresh fehlgeschlagen (z. B. abgelaufene Session): erneut einloggen.
            _LOGGER.debug("Token-Refresh fehlgeschlagen; vollständiger Login wird erneut versucht")
            return await self.async_login()
        _LOGGER.debug("Access-Token ist gültig; kein Refresh erforderlich")
        return True

    async def _async_get_json(self, url: str, params: dict | None = None) -> dict:
        """GET a JSON endpoint with bearer auth, refreshing the token once on 401/403."""
        if not await self._async_ensure_valid_token():
            raise EnviamAuthError("Kein gültiger Access-Token verfügbar.")
        try:
            headers = {"Authorization": f"Bearer {self._access_token}"}
            async with self.session.get(url, headers=headers, params=params) as response:
                _LOGGER.debug("API-Antwort: url=%s, status=%s", url, response.status)
                if response.status in (401, 403):
                    _LOGGER.debug("API verweigert Zugriff; Refresh und Retry werden versucht")
                    if not await self._async_refresh_token():
                        raise EnviamAuthError("Token-Refresh fehlgeschlagen.")
                    headers = {"Authorization": f"Bearer {self._access_token}"}
                    async with self.session.get(url, headers=headers, params=params) as retry:
                        _LOGGER.debug("API-Retry-Antwort: url=%s, status=%s", url, retry.status)
                        if retry.status in (401, 403):
                            raise EnviamAuthError("Zugriff trotz gültigem Refresh-Token verweigert.")
                        retry.raise_for_status()
                        data = await retry.json(content_type=None)
                        _LOGGER.debug(
                            "API-Retry erfolgreich: url=%s, top_level_keys=%s",
                            url,
                            list(data) if isinstance(data, dict) else type(data).__name__,
                        )
                        return data
                response.raise_for_status()
                data = await response.json(content_type=None)
                _LOGGER.debug(
                    "API erfolgreich: url=%s, top_level_keys=%s",
                    url,
                    list(data) if isinstance(data, dict) else type(data).__name__,
                )
                return data
        except EnviamAuthError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise EnviamConnectionError(str(err)) from err

    async def async_get_energy_data(self) -> dict:
        _LOGGER.debug("Energy-Flow-Request vorbereitet: GET %s", ENERGY_FLOW_URL)
        return await self._async_get_json(ENERGY_FLOW_URL)

    async def async_get_analytics_overview(
        self, start: datetime, end: datetime, resolution: str | None = None
    ) -> dict:
        """Return the work (Wh) per interval for the given time range."""
        params = {
            "from": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "type": ANALYTICS_TYPE,
        }
        if resolution:
            params["resolution"] = resolution
        _LOGGER.debug(
            "Analytics-Overview-Request vorbereitet: GET %s, params=%s",
            ANALYTICS_OVERVIEW_URL,
            params,
        )
        return await self._async_get_json(ANALYTICS_OVERVIEW_URL, params=params)
