"""Constants for the Envertech EVT Local integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "envertech_local"

CONF_SERIAL = "serial"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=120)

# Device info
MANUFACTURER = "Envertech"
MODEL = "EVT2000SE"
