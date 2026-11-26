"""HTTP client for the Heatmaster LOGO! 8 AJAX interface."""
from __future__ import annotations

from typing import Any

import binascii
import logging
import time
from xml.dom.minidom import Element, parseString
from xml.parsers.expat import ExpatError

import requests

_LOGGER = logging.getLogger(__name__)


class HeatmasterAjax:
    """Communicate with the Heatmaster LOGO! 8 controller over HTTP."""

    _STATUS_MESSAGE_IDS = {0: 0, 1: 1, 2: 14}
    _STATUS_LABELS = {0: "Heating", 1: "Idle", 2: "Cold Start"}
    _RETRY_DELAYS = (1, 2)
    _REQUEST_TIMEOUT = (3, 5)

    def __init__(
        self,
        ip_address: str,
        username: str = "Web User",
        password: str = "heatmaster",
        no_login: bool = False,
    ) -> None:
        """Initialize without network I/O; login lazily on the first poll."""
        self.ip_address = ip_address
        self.url = f"http://{ip_address}/AJAX"
        self.username = username
        self.password = password
        self.status = 1
        self.bypass = "Off"
        self.alarm = "Off"
        self.auth_cookie: dict[str, str] | None = None
        self._session = requests.Session()
        # Keep accepting the old argument so existing callers remain compatible.
        self._no_login = no_login

    def login(self) -> bool:
        """Perform the original two-step challenge, with bounded retries."""
        self.auth_cookie = None
        for attempt in range(len(self._RETRY_DELAYS) + 1):
            try:
                challenge = self._session.post(
                    self.url,
                    data="UAMCHAL:3,4,1,2,3,4",
                    timeout=self._REQUEST_TIMEOUT,
                )
                challenge.raise_for_status()
                challenge_fields = challenge.text.strip().split(",")
                if len(challenge_fields) < 3 or challenge_fields[0] != "700":
                    raise ValueError("Malformed LOGO! challenge response")

                server_key = int(challenge_fields[2])
                password_challenge = self._generate_password_challenge(server_key)
                server_challenge = self._generate_server_challenge(server_key)
                login_response = self._session.post(
                    self.url,
                    data=f"UAMLOGIN:{self.username},{password_challenge},{server_challenge}",
                    cookies={"Security-Hint": challenge_fields[1]},
                    timeout=self._REQUEST_TIMEOUT,
                )
                login_response.raise_for_status()
                login_fields = login_response.text.strip().split(",")
                if len(login_fields) < 2 or login_fields[0] != "700" or not login_fields[1]:
                    raise ValueError("Malformed LOGO! login response")

                self.auth_cookie = {"Security-Hint": login_fields[1]}
                _LOGGER.info("Login for Heatmaster at %s succeeded", self.ip_address)
                return True
            except (requests.exceptions.RequestException, ValueError) as err:
                _LOGGER.warning(
                    "Heatmaster login attempt %s/%s failed: %s",
                    attempt + 1,
                    len(self._RETRY_DELAYS) + 1,
                    err,
                )
                if attempt < len(self._RETRY_DELAYS):
                    time.sleep(self._RETRY_DELAYS[attempt])
        return False

    def _generate_server_challenge(self, server_key: int) -> int:
        """Generate the server challenge response with the existing protocol."""
        return 1 ^ 2 ^ 3 ^ 4 ^ server_key

    def _generate_password_challenge(self, server_key: int) -> int:
        """Generate the CRC32 password challenge with the existing protocol."""
        password_string = f"{self.password}+{server_key}"
        return binascii.crc32(password_string.encode("utf-8")) ^ server_key

    def _set_status(self, status_text: list[Any]) -> bool:
        """Update primary status and separately track alarm and bypass overlays."""
        previous_status = self.status
        status_label = ""
        bypass_label = ""
        for item in status_text:
            item_id = item.getAttribute("id")
            value = item.getAttribute("v").strip()
            if "BYPASS" in value.upper() or "BY-PASS" in value.upper():
                bypass_label = value
            if item_id == "1":
                status_label = value

        if "Heating" in status_label:
            self.status = 0
            self.alarm = "Off"
        elif "Idle" in status_label:
            self.status = 1
            self.alarm = "Off"
        elif "Cold" in status_label:
            self.status = 2
            self.alarm = "Off"
        elif "ALARM" in status_label.upper():
            self.alarm = "On"
        elif status_label:
            _LOGGER.warning("Unrecognized Heatmaster status label: %r", status_label)

        self.bypass = "On" if bypass_label else "Off"

        if self.status != previous_status:
            _LOGGER.info("Heatmaster status changed to %s", self._STATUS_LABELS[self.status])
        if self.alarm == "On":
            _LOGGER.warning("Heatmaster alarm is active; primary status remains %s", self._STATUS_LABELS[self.status])
        return self.status != previous_status

    def _fetch_raw_data(self) -> str:
        """Fetch the message associated with the controller's current status."""
        response = self._session.post(
            self.url,
            data=f"MSGGET:bm,{self._STATUS_MESSAGE_IDS[self.status]}",
            cookies=self.auth_cookie,
            timeout=self._REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    def _fetch_authenticated_data(self) -> str | None:
        """Login lazily and repeat the data request after session expiration."""
        if self.auth_cookie is None and not self.login():
            return None

        payload = self._fetch_raw_data()
        if "Session Expired" not in payload:
            return payload

        _LOGGER.warning("Heatmaster session expired; refreshing login")
        if not self.login():
            return None
        payload = self._fetch_raw_data()
        if "Session Expired" in payload:
            _LOGGER.error("Heatmaster session expired again immediately after login")
            return None
        return payload

    def _parse_payload(self, payload: str) -> tuple[dict[str, str | float], bool]:
        """Parse a message by XML attribute names and tolerate incomplete data."""
        if not payload or not payload.strip():
            _LOGGER.warning("Heatmaster returned an empty AJAX response")
            return {}, False
        try:
            document = parseString(payload)
        except (ExpatError, TypeError, ValueError) as err:
            _LOGGER.warning("Heatmaster returned malformed XML: %s", err)
            return {}, False

        response: dict[str, str | float] = {"Status": self._STATUS_LABELS[self.status]}
        status_tags = document.getElementsByTagName("t")
        if status_tags:
            status_changed = self._set_status(status_tags)
            response["Status"] = self._STATUS_LABELS[self.status]
            response["Alarm"] = self.alarm
            response["Bypass"] = self.bypass
            if self.status == 2:
                # Owner confirmed the top damper reads MaxAir during Cold Start.
                response["Top Damper"] = "MaxAir"
            return response, status_changed

        key_by_id = {
            "0": "Temperature",
            "1": "o2",
            "2": "Top Damper",
            "3": "Bot Damper",
        }
        for item in document.getElementsByTagName("p"):
            item_id = item.getAttribute("id")
            value = item.getAttribute("v").strip()
            if item_id not in key_by_id or not value or value.lower() == "n":
                continue
            try:
                response[key_by_id[item_id]] = float(value)
            except ValueError:
                _LOGGER.warning(
                    "Ignoring non-numeric Heatmaster p id=%s value %r",
                    item_id,
                    value,
                )

        response["Alarm"] = self.alarm
        response["Bypass"] = self.bypass
        if self.status == 2:
            response["Top Damper"] = "MaxAir"
        return response, False

    def get_data(self) -> dict[str, str | float] | None:
        """Fetch status and readings; failures return None rather than aborting HA."""
        try:
            payload = self._fetch_authenticated_data()
            if payload is None:
                return None

            response, status_changed = self._parse_payload(payload)
            if not response:
                return None

            if status_changed:
                # Transition replies contain only screen labels; fetch once using
                # the new message ID so this poll returns the current screen.
                payload = self._fetch_authenticated_data()
                if payload is None:
                    return response
                refreshed, _ = self._parse_payload(payload)
                if refreshed:
                    response.update(refreshed)

            _LOGGER.debug("Polled Heatmaster data: %s", response)
            return response
        except requests.exceptions.RequestException as err:
            _LOGGER.warning("Unable to fetch Heatmaster at %s: %s", self.ip_address, err)
            return None