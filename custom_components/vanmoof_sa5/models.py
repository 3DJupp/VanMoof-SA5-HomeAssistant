"""Data models for the VanMoof SA5 integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class VanMoofBike:
    """VanMoof bike metadata plus per-bike credentials."""

    unique_id: str
    name: str
    frame_number: str
    bike_api_id: str
    ble_profile: str
    model: str
    frame_serial: str | None = None
    main_ecu_serial: str | None = None
    owner_name: str | None = None
    certificate: str | None = None
    certificate_expiry: int | None = None
    private_key: str | None = None
    public_key: str | None = None
    ble_address: str | None = None

    @property
    def display_model(self) -> str:
        """Return a friendly model label."""
        return self.model or self.ble_profile


@dataclass(slots=True)
class BikeState:
    """Runtime state fetched from the bike over BLE."""

    available: bool
    in_range: bool
    battery_level: int | None = None
    module_battery: int | None = None
    locked: bool | None = None
    distance_km: float | None = None
    power_level: str | None = None
    light_mode: str | None = None
    speed_limit: str | None = None
    speed_kmh: int | None = None
    calories: int | None = None
    connection_state: str = "disconnected"
    last_seen: datetime | None = None
    firmware_info: str | None = None
    errors: str | None = None
    raw_topics: dict[int, Any] = field(default_factory=dict)
