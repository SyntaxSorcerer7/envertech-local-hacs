"""Config flow for Envertech EVT Local integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST

from .const import CONF_SERIAL, DOMAIN
from .protocol import EnvertechConnection

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_SERIAL): str,
    }
)


class EnvertechLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Envertech EVT Local."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            serial_str = user_input[CONF_SERIAL].strip()

            # Parse serial as hex
            try:
                if serial_str.startswith("0x") or serial_str.startswith("0X"):
                    serial = int(serial_str, 16)
                else:
                    serial = int(serial_str, 16)
            except ValueError:
                errors[CONF_SERIAL] = "invalid_serial"

            if not errors:
                # Test connection
                conn = EnvertechConnection(host, serial)
                try:
                    await conn.get_live_data()
                    await conn.disconnect()
                except (ConnectionError, OSError):
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(f"{serial:08X}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"Envertech {serial:08X}",
                        data={
                            CONF_HOST: host,
                            CONF_SERIAL: serial,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
