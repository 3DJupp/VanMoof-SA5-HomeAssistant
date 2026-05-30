"""Button entities for VanMoof SA5."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .protocol import Topic


@dataclass(frozen=True, kw_only=True)
class VanMoofButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[VanMoofDataUpdateCoordinator, str], Awaitable[None]]


async def _async_refresh(coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
    await coordinator.async_manual_refresh()


async def _async_find_my(coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
    await coordinator.async_set_bike_topic(bike_id, Topic.FIND_MY, 1)


async def _async_ring_bell(coordinator: VanMoofDataUpdateCoordinator, bike_id: str) -> None:
    await coordinator.async_set_bike_topic(bike_id, Topic.BELL_SOUND, 1)


BUTTONS: tuple[VanMoofButtonDescription, ...] = (
    VanMoofButtonDescription(
        key="refresh",
        translation_key="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=_async_refresh,
    ),
    VanMoofButtonDescription(
        key="find_my",
        translation_key="find_my",
        press_fn=_async_find_my,
    ),
    VanMoofButtonDescription(
        key="ring_bell",
        translation_key="ring_bell",
        press_fn=_async_ring_bell,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[VanMoofButton] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(
            VanMoofButton(coordinator, bike_id, description)
            for description in BUTTONS
        )
    async_add_entities(entities)


class VanMoofButton(VanMoofEntity, ButtonEntity):
    """VanMoof button entity."""

    entity_description: VanMoofButtonDescription

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
        description: VanMoofButtonDescription,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self.entity_description = description
        self._attr_unique_id = f"{bike_id}_{description.key}"

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator, self._bike_id)
