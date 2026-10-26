"""Switch entities for VanMoof SA5."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .models import BikeState
from .protocol import (
    BleWrite,
    write_alarm_mode,
    write_brake_light,
    write_indicator_light,
)


@dataclass(frozen=True, kw_only=True)
class VanMoofSwitchDescription(SwitchEntityDescription):
    """Switch backed by a boolean BLE topic."""

    value_fn: Callable[[BikeState], bool | None]
    write_fn: Callable[[bool], BleWrite]


SWITCHES: tuple[VanMoofSwitchDescription, ...] = (
    VanMoofSwitchDescription(
        key="alarm",
        translation_key="alarm",
        value_fn=lambda state: state.alarm_enabled,
        write_fn=write_alarm_mode,
    ),
    VanMoofSwitchDescription(
        key="brake_light",
        translation_key="brake_light",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda state: state.brake_light,
        write_fn=write_brake_light,
    ),
    VanMoofSwitchDescription(
        key="indicator_light",
        translation_key="indicator_light",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda state: state.indicator_light,
        write_fn=write_indicator_light,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(VanMoofSwitch(coordinator, bike_id, d) for d in SWITCHES)
        entities.append(VanMoofTouchUnlockSwitch(coordinator, bike_id))
    async_add_entities(entities)


class VanMoofSwitch(VanMoofEntity, SwitchEntity):
    """Switch entity writing to a bike topic."""

    entity_description: VanMoofSwitchDescription

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
        description: VanMoofSwitchDescription,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self.entity_description = description
        self._attr_unique_id = f"{bike_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.bike_state)

    @property
    def available(self) -> bool:
        return self.is_on is not None or self.bike_state.available

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_send_writes(
            self._bike_id, [self.entity_description.write_fn(True)]
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_send_writes(
            self._bike_id, [self.entity_description.write_fn(False)]
        )


class VanMoofTouchUnlockSwitch(VanMoofEntity, SwitchEntity, RestoreEntity):
    """Proximity unlock. The bike cannot report this, so the state is remembered."""

    _attr_translation_key = "touch_unlock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_touch_unlock"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self.coordinator.touch_unlock_for(self._bike_id).enabled = last.state == STATE_ON

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.touch_unlock_for(self._bike_id).enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_touch_unlock(self._bike_id, enabled=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_touch_unlock(self._bike_id, enabled=False)
