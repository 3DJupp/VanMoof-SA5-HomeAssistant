"""Switch entities for VanMoof SA5."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
        VanMoofAlarmSwitch(coordinator, bike_id)
        for bike_id in coordinator.data.bikes
    )


class VanMoofAlarmSwitch(VanMoofEntity, SwitchEntity):
    """Enables or disables the VanMoof anti-theft alarm."""

    _attr_translation_key = "alarm"

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_alarm"

    @property
    def is_on(self) -> bool | None:
        state = self.bike_state.alarm_state
        if state is None:
            return None
        return state != 0

    @property
    def available(self) -> bool:
        return self.bike_state.available

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_set_bike_topic(self._bike_id, Topic.ALARM, 1)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_set_bike_topic(self._bike_id, Topic.ALARM, 0)
