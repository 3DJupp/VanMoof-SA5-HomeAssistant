"""Lock entity for VanMoof SA5."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .protocol import Topic


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VanMoofLock(coordinator, bike_id)
        for bike_id in coordinator.data.bikes
    )


class VanMoofLock(VanMoofEntity, LockEntity):
    """Controls the electronic lock of a VanMoof bike."""

    _attr_translation_key = "lock"

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_lock"

    @property
    def is_locked(self) -> bool | None:
        return self.bike_state.locked

    @property
    def available(self) -> bool:
        return self.bike_state.available

    async def async_lock(self, **kwargs: object) -> None:
        await self.coordinator.async_set_bike_topic(self._bike_id, Topic.LOCK_STATE, 3)

    async def async_unlock(self, **kwargs: object) -> None:
        await self.coordinator.async_set_bike_topic(self._bike_id, Topic.LOCK_STATE, 1)
