"""Lock entity for VanMoof SA5 (unlock only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .protocol import write_unlock


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VanMoofLock(coordinator, bike_id) for bike_id in coordinator.data.bikes)


class VanMoofLock(VanMoofEntity, LockEntity):
    """Rear wheel lock of the bike.

    The VanMoof app can only unlock the bike over BLE. Locking is done with
    the button on the bike, so ``lock`` is intentionally not supported.
    """

    _attr_translation_key = "lock"

    def __init__(self, coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_lock"

    @property
    def available(self) -> bool:
        # Unlocking needs the bike in range, but the last known state is shown
        # even while it is away.
        return self.bike_state.locked is not None or self.bike_state.available

    @property
    def is_locked(self) -> bool | None:
        return self.bike_state.locked

    @property
    def is_unlocking(self) -> bool:
        return self.bike_state.lock_state == "unlocking"

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_send_writes(self._bike_id, [write_unlock()])

    async def async_lock(self, **kwargs: Any) -> None:
        raise HomeAssistantError(
            "The VanMoof SA5 can only be locked with the button on the bike"
        )
