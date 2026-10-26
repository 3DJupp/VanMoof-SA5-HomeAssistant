"""Coordinator for the VanMoof SA5 integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VanMoofApiClient, VanMoofApiError
from .ble import VanMoofBikeBleClient, VanMoofBleConnectError, VanMoofBleError
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    WEEKLY_REFRESH_SECONDS,
)
from .models import BikeState, VanMoofBike
from .protocol import BleWrite, write_touch_unlock

_LOGGER = logging.getLogger(__name__)

DEFAULT_TOUCH_UNLOCK_DISTANCE = "average"


def _connection_state_for(err: VanMoofBleError) -> str:
    if isinstance(err, VanMoofBleConnectError):
        return "unreachable"
    if "No nearby VanMoof BLE advertisements were found" in str(err):
        return "out_of_range"
    return "error"


@dataclass(slots=True)
class VanMoofCoordinatorData:
    """Coordinator payload."""

    bikes: dict[str, VanMoofBike]
    states: dict[str, BikeState]
    weekly: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class TouchUnlockSettings:
    """Touch unlock settings. The bike cannot report them, so HA remembers them."""

    enabled: bool = False
    distance: str = DEFAULT_TOUCH_UNLOCK_DISTANCE


class VanMoofDataUpdateCoordinator(DataUpdateCoordinator[VanMoofCoordinatorData]):
    """Coordinator that refreshes bikes sequentially over BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: VanMoofApiClient,
    ) -> None:
        self.entry = entry
        self.api = api
        self.touch_unlock: dict[str, TouchUnlockSettings] = {}
        self._ble_locks: dict[str, asyncio.Lock] = {}
        self._weekly: dict[str, dict[str, Any]] = {}
        self._weekly_fetched: dict[str, float] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )

    def _lock_for(self, bike_id: str) -> asyncio.Lock:
        return self._ble_locks.setdefault(bike_id, asyncio.Lock())

    async def _async_update_data(self) -> VanMoofCoordinatorData:
        try:
            await self.api.async_ensure_certificates(list(self.api.bikes.values()))
        except VanMoofApiError as err:
            if "401" in str(err) or "403" in str(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

        states: dict[str, BikeState] = {}
        for bike in self.api.bikes.values():
            previous_state = self.data.states.get(bike.unique_id) if self.data else None
            try:
                async with self._lock_for(bike.unique_id):
                    state, address = await VanMoofBikeBleClient(
                        bike, self.hass
                    ).async_fetch_state()
                if address and bike.ble_address != address:
                    bike.ble_address = address
                state.last_seen = dt_util.utcnow()
                state.carry_over(previous_state)
                states[bike.unique_id] = state
            except VanMoofBleError as err:
                state = BikeState(
                    available=False,
                    in_range=False,
                    connection_state=_connection_state_for(err),
                    errors=str(err),
                )
                state.carry_over(previous_state)
                states[bike.unique_id] = state

            await self._async_refresh_weekly(bike)

        self.hass.async_create_task(self._async_persist_entry())
        return VanMoofCoordinatorData(
            bikes=dict(self.api.bikes), states=states, weekly=dict(self._weekly)
        )

    async def _async_refresh_weekly(self, bike: VanMoofBike) -> None:
        """Refresh the weekly ride summary from the VanMoof cloud (rarely)."""
        loop_time = self.hass.loop.time()
        last = self._weekly_fetched.get(bike.unique_id)
        if last is not None and loop_time - last < WEEKLY_REFRESH_SECONDS:
            return
        self._weekly_fetched[bike.unique_id] = loop_time
        try:
            summary = await self.api.async_get_weekly_summary(bike)
        except VanMoofApiError as err:
            _LOGGER.debug("Could not fetch weekly rides for %s: %s", bike.unique_id, err)
            return
        if summary:
            self._weekly[bike.unique_id] = summary

    async def _async_persist_entry(self) -> None:
        new_data = self.api.export_entry_data()
        if new_data != self.entry.data:
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

    async def async_manual_refresh(self) -> None:
        """Run an immediate refresh."""
        await self.async_request_refresh()

    async def async_send_writes(self, bike_id: str, writes: list[BleWrite]) -> None:
        """Send ``writes`` to a bike and publish the state read back afterwards."""
        bike = self.api.bikes.get(bike_id)
        if bike is None:
            raise HomeAssistantError(f"Unknown VanMoof bike {bike_id}")

        try:
            await self.api.async_ensure_certificates([bike])
            async with self._lock_for(bike_id):
                state, address = await VanMoofBikeBleClient(bike, self.hass).async_execute(
                    writes
                )
        except (VanMoofApiError, VanMoofBleError) as err:
            raise HomeAssistantError(f"Could not send command to {bike.name}: {err}") from err

        if address and bike.ble_address != address:
            bike.ble_address = address

        if state is not None and self.data is not None:
            previous = self.data.states.get(bike_id)
            state.last_seen = dt_util.utcnow()
            state.carry_over(previous)
            states = dict(self.data.states)
            states[bike_id] = state
            self.async_set_updated_data(
                VanMoofCoordinatorData(
                    bikes=dict(self.api.bikes), states=states, weekly=dict(self._weekly)
                )
            )

    # ------------------------------------------------------------------
    # Touch unlock (write-only on the bike, so the settings live in HA)
    # ------------------------------------------------------------------

    def touch_unlock_for(self, bike_id: str) -> TouchUnlockSettings:
        """Return the remembered touch unlock settings for a bike."""
        return self.touch_unlock.setdefault(bike_id, TouchUnlockSettings())

    async def async_set_touch_unlock(
        self,
        bike_id: str,
        *,
        enabled: bool | None = None,
        distance: str | None = None,
    ) -> None:
        """Update and send the touch unlock configuration."""
        settings = self.touch_unlock_for(bike_id)
        new_enabled = settings.enabled if enabled is None else enabled
        new_distance = settings.distance if distance is None else distance
        await self.async_send_writes(bike_id, [write_touch_unlock(new_enabled, new_distance)])
        settings.enabled = new_enabled
        settings.distance = new_distance
        self.async_update_listeners()
