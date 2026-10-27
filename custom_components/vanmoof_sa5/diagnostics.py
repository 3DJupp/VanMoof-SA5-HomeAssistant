"""Diagnostics support for VanMoof SA5."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_APP_TOKEN,
    CONF_AUTH_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_UNLOCK_CODE,
    DOMAIN,
)
from .coordinator import VanMoofDataUpdateCoordinator
from .protocol import TOPIC_NAMES

TO_REDACT = {
    "email",
    "password",
    CONF_AUTH_TOKEN,
    CONF_APP_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_UNLOCK_CODE,
    "certificate",
    "private_key",
    "public_key",
    "frame_number",
    "frame_serial",
    "main_ecu_serial",
    "owner_name",
    "unique_id",
    "bike_api_id",
    "ble_address",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    bikes = []
    for bike_id, bike in coordinator.data.bikes.items():
        state = coordinator.data.states.get(bike_id)
        state_data = asdict(state) if state else {}
        raw_topics = state_data.pop("raw_topics", {})
        bikes.append(
            {
                "bike": async_redact_data(asdict(bike), TO_REDACT),
                "state": _jsonable(state_data),
                # Raw topic values as received over BLE, keyed by topic number
                "raw_topics": {
                    str(topic): {
                        "name": TOPIC_NAMES.get(topic, f"topic_{topic}"),
                        "value": _jsonable(value),
                    }
                    for topic, value in sorted(raw_topics.items())
                },
            }
        )

    return {
        "entry": {
            "data": async_redact_data(
                {key: value for key, value in entry.data.items() if key != "bikes"},
                TO_REDACT,
            ),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "bikes": bikes,
    }


def _jsonable(value: Any) -> Any:
    """Convert decoded CBOR values into JSON-serializable data."""
    if isinstance(value, (bytes, bytearray)):
        return {"bytes_hex": bytes(value).hex()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
