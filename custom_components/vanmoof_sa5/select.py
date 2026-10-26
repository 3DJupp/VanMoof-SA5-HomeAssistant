"""Select entities for VanMoof SA5."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .models import BikeState
from .protocol import (
    ANIMATION_THEMES,
    BELL_SOUNDS,
    LIGHT_MODES,
    POWER_LEVEL_OPTIONS,
    REGIONS,
    RIDING_DISPLAY_MODES,
    TOUCH_UNLOCK_RSSI,
    BleWrite,
    write_animation_theme,
    write_bell_sound,
    write_light_mode,
    write_power_level,
    write_region,
    write_riding_display,
)


@dataclass(frozen=True, kw_only=True)
class VanMoofSelectDescription(SelectEntityDescription):
    """Select backed by a BLE topic."""

    value_fn: Callable[[BikeState], str | None]
    write_fn: Callable[[str], BleWrite]


SELECTS: tuple[VanMoofSelectDescription, ...] = (
    VanMoofSelectDescription(
        key="assist_level",
        translation_key="assist_level",
        options=list(POWER_LEVEL_OPTIONS.values()),
        value_fn=lambda state: state.power_level,
        write_fn=lambda option: write_power_level(int(option) if option.isdigit() else 0),
    ),
    VanMoofSelectDescription(
        key="light_mode_select",
        translation_key="light_mode_select",
        options=list(LIGHT_MODES.values()),
        value_fn=lambda state: state.light_mode,
        write_fn=write_light_mode,
    ),
    VanMoofSelectDescription(
        key="bell_sound_select",
        translation_key="bell_sound_select",
        options=list(BELL_SOUNDS.values()),
        value_fn=lambda state: state.bell_sound,
        write_fn=write_bell_sound,
    ),
    # Changes the legal speed limit (EU 25, US 32, Japan 24, offroad unrestricted).
    # Disabled by default; enabling and using it is the owner's responsibility.
    VanMoofSelectDescription(
        key="region_select",
        translation_key="region_select",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        options=list(REGIONS.values()),
        value_fn=lambda state: state.region,
        write_fn=write_region,
    ),
    VanMoofSelectDescription(
        key="riding_display",
        translation_key="riding_display",
        entity_category=EntityCategory.CONFIG,
        options=list(RIDING_DISPLAY_MODES.values()),
        value_fn=lambda state: state.riding_display,
        write_fn=write_riding_display,
    ),
    VanMoofSelectDescription(
        key="animation_theme",
        translation_key="animation_theme",
        entity_category=EntityCategory.CONFIG,
        options=list(ANIMATION_THEMES.values()),
        value_fn=lambda state: state.animation_theme,
        write_fn=write_animation_theme,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(VanMoofSelect(coordinator, bike_id, d) for d in SELECTS)
        entities.append(VanMoofTouchUnlockDistanceSelect(coordinator, bike_id))
    async_add_entities(entities)


class VanMoofSelect(VanMoofEntity, SelectEntity):
    """Select entity writing to a bike topic."""

    entity_description: VanMoofSelectDescription

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
        description: VanMoofSelectDescription,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self.entity_description = description
        self._attr_unique_id = f"{bike_id}_{description.key}"

    @property
    def current_option(self) -> str | None:
        return self.entity_description.value_fn(self.bike_state)

    @property
    def available(self) -> bool:
        # Keep showing the last known setting while the bike is away; a write
        # fails with a clear error if the bike cannot be reached.
        return self.current_option is not None or self.bike_state.available

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_send_writes(
            self._bike_id, [self.entity_description.write_fn(option)]
        )


class VanMoofTouchUnlockDistanceSelect(VanMoofEntity, SelectEntity, RestoreEntity):
    """How close the phone has to be for touch unlock (RSSI threshold)."""

    _attr_translation_key = "touch_unlock_distance"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(TOUCH_UNLOCK_RSSI)

    def __init__(self, coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
        super().__init__(coordinator, bike_id)
        self._attr_unique_id = f"{bike_id}_touch_unlock_distance"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in TOUCH_UNLOCK_RSSI:
            self.coordinator.touch_unlock_for(self._bike_id).distance = last.state

    @property
    def available(self) -> bool:
        return True

    @property
    def current_option(self) -> str | None:
        return self.coordinator.touch_unlock_for(self._bike_id).distance

    async def async_select_option(self, option: str) -> None:
        settings = self.coordinator.touch_unlock_for(self._bike_id)
        if settings.enabled:
            await self.coordinator.async_set_touch_unlock(self._bike_id, distance=option)
        else:
            # Touch unlock is off: just remember the distance for later.
            settings.distance = option
            self.async_write_ha_state()
