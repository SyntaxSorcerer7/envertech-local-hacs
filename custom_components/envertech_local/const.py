"""Constants for the Envertech EVT Local integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "envertech_local"

CONF_SERIAL = "serial"
CONF_PRICE_PER_KWH = "price_per_kwh"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=120)
DEFAULT_PRICE_PER_KWH = 0.30

# Device info
MANUFACTURER = "Envertech"
MODEL = "EVT2000SE"
