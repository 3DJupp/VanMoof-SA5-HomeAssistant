"""Lock entity for VanMoof SA5 (unlock only, protected by a code)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_UNLOCK_CODE, DOMAIN
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

    Unlocking is a security feature, so the entity is disabled by default and
    only works once an unlock code is set in the integration options. The code
    must be passed with every ``lock.unlock`` call (Home Assistant asks for it
    in the UI). Locking is done with the button on the bike.
    """

    _attr_translation_key = "lock"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_lock"

    @property
    def _configured_code(self) -> str:
        return str(self.coordinator.entry.options.get(CONF_UNLOCK_CODE, "") or "")

    @property
    def code_format(self) -> str | None:
        return r".+" if self._configured_code else None

    @property
    def available(self) -> bool:
        return self.bike_state.locked is not None or self.bike_state.available

    @property
    def is_locked(self) -> bool | None:
        return self.bike_state.locked

    @property
    def is_unlocking(self) -> bool:
        return self.bike_state.lock_state == "unlocking"

    async def async_unlock(self, **kwargs: Any) -> None:
        configured = self._configured_code
        if not configured:
            raise ServiceValidationError(
                "Set an unlock code in the VanMoof integration options to enable unlocking"
            )
        if kwargs.get("code") != configured:
            raise ServiceValidationError("Wrong or missing unlock code")
        await self.coordinator.async_send_writes(self._bike_id, [write_unlock()])

    async def async_lock(self, **kwargs: Any) -> None:
        raise HomeAssistantError(
            "The VanMoof SA5 can only be locked with the button on the bike"
        )
