"""Binary sensors for VanMoof SA5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofDataUpdateCoordinator
from .entity import VanMoofEntity


@dataclass(frozen=True, kw_only=True)
class VanMoofBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[Any], Any]
    attrs_fn: Callable[[Any], dict[str, Any]] | None = None


def _find_my_enabled(state: Any) -> bool | None:
    return (state.find_my_state or {}).get("enabled")


def _find_my_attributes(state: Any) -> dict[str, Any]:
    """Return the Find My status fields reported by the bike."""
    find_my = state.find_my_state or {}
    return {key: find_my.get(key) for key in ("ready", "paired", "pairing", "provisioned")}


BINARY_SENSORS: tuple[VanMoofBinarySensorDescription, ...] = (
    VanMoofBinarySensorDescription(
        key="locked",
        translation_key="locked",
        value_fn=lambda state: state.locked,
    ),
    VanMoofBinarySensorDescription(
        key="find_my",
        translation_key="find_my",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_find_my_enabled,
        attrs_fn=_find_my_attributes,
    ),
    VanMoofBinarySensorDescription(
        key="in_range",
        translation_key="in_range",
        device_class=BinarySensorDeviceClass.PRESENCE,
        value_fn=lambda state: state.in_range,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VanMoofDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[VanMoofBinarySensor] = []
    for bike_id in coordinator.data.bikes:
        entities.extend(
            VanMoofBinarySensor(coordinator, bike_id, description)
            for description in BINARY_SENSORS
        )
    async_add_entities(entities)


class VanMoofBinarySensor(VanMoofEntity, BinarySensorEntity):
    """VanMoof binary sensor."""

    entity_description: VanMoofBinarySensorDescription

    def __init__(
        self,
        coordinator: VanMoofDataUpdateCoordinator,
        bike_id: str,
        description: VanMoofBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, bike_id)
        self.entity_description = description
        self._attr_unique_id = f"{bike_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.bike_state)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        return None if attrs_fn is None else attrs_fn(self.bike_state)

    @property
    def available(self) -> bool:
        return self.bike_state.available or self.entity_description.key == "in_range"
