"""Select entities for VanMoof SA5."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity
from .protocol import Topic


@dataclass(frozen=True, kw_only=True)
class VanMoofSelectDescription(SelectEntityDescription):
    topic: Topic
    options_map: dict[str, int]
    current_fn: Callable[[Any], int | None]


SELECTS: tuple[VanMoofSelectDescription, ...] = (
    VanMoofSelectDescription(
        key="bell_sound",
        translation_key="bell_sound",
        topic=Topic.BELL_SOUND,
        options_map={"1": 1, "2": 2, "3": 3, "4": 4},
        current_fn=lambda state: state.raw_topics.get(Topic.BELL_SOUND),
    ),
    VanMoofSelectDescription(
        key="speed_limit",
        translation_key="speed_limit",
        topic=Topic.GEAR,
        options_map={"25 km/h": 0, "32 km/h": 1, "24 km/h": 2},
        current_fn=lambda state: state.raw_topics.get(Topic.GEAR),
    ),
    VanMoofSelectDescription(
        key="light_mode_select",
        translation_key="light_mode_select",
        topic=Topic.LIGHT_MODE,
        options_map={"off": 0, "on": 1, "halo": 2, "auto": 3},
        current_fn=lambda state: state.raw_topics.get(Topic.LIGHT_MODE),
    ),
    VanMoofSelectDescription(
        key="power_level_select",
        translation_key="power_level_select",
        topic=Topic.POWER_LEVEL,
        options_map={"0": 0, "1": 1, "2": 2, "3": 3, "4": 4},
        current_fn=lambda state: state.raw_topics.get(Topic.POWER_LEVEL),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[VanMoofSelect] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(
            VanMoofSelect(coordinator, bike_id, description)
            for description in SELECTS
        )
    async_add_entities(entities)


class VanMoofSelect(VanMoofEntity, SelectEntity):
    """VanMoof select entity for controllable bike settings."""

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
        self._attr_options = list(description.options_map.keys())
        self._reverse_map = {v: k for k, v in description.options_map.items()}

    @property
    def current_option(self) -> str | None:
        raw = self.entity_description.current_fn(self.bike_state)
        if raw is None:
            return None
        return self._reverse_map.get(int(raw))

    @property
    def available(self) -> bool:
        return self.bike_state.available

    async def async_select_option(self, option: str) -> None:
        raw_value = self.entity_description.options_map[option]
        await self.coordinator.async_set_bike_topic(
            self._bike_id, self.entity_description.topic, raw_value
        )
