"""Button entities for VanMoof SA5."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity


BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="refresh",
        translation_key="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    ) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[VanMoofRefreshButton] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(
            VanMoofRefreshButton(coordinator, bike_id, description)
            for description in BUTTONS
        )
    async_add_entities(entities)


class VanMoofRefreshButton(VanMoofEntity, ButtonEntity):
    """Manual refresh button."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self.entity_description = description
        self._attr_unique_id = f"{bike_id}_{description.key}"

    async def async_press(self) -> None:
        await self.coordinator.async_manual_refresh()
