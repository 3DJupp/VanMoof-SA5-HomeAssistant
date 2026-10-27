"""Coordinator for the VanMoof SA5 integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VanMoofApiClient, VanMoofApiError
from .ble import (
    VanMoofBikeBleClient,
    VanMoofBleConnectError,
    VanMoofBleError,
    is_vanmoof_advertisement,
)
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    SERVICE_UUID,
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
        self.options = dict(entry.options)
        self.touch_unlock: dict[str, TouchUnlockSettings] = {}
        self._ble_locks: dict[str, asyncio.Lock] = {}
        self._tracked_addresses: set[str] = set()
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

    @callback
    def async_start_presence_tracking(self) -> None:
        """Follow bike advertisements passively via the Bluetooth integration."""
        self.entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                self._async_handle_advertisement,
                bluetooth.BluetoothCallbackMatcher(
                    service_uuid=SERVICE_UUID, connectable=False
                ),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        for bike in self.api.bikes.values():
            self._async_track_unavailable(bike)

    @callback
    def _async_track_unavailable(self, bike: VanMoofBike) -> None:
        address = bike.ble_address
        if not address or address.upper() in self._tracked_addresses:
            return
        self._tracked_addresses.add(address.upper())
        self.entry.async_on_unload(
            bluetooth.async_track_unavailable(
                self.hass,
                self._async_handle_unavailable,
                address,
                connectable=False,
            )
        )

    @callback
    def _async_handle_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if not is_vanmoof_advertisement(service_info) or not self.data:
            return
        bike = self._bike_for_address(service_info.address)
        if bike is None:
            # Unknown address: a bike without a learned address may be nearby
            if any(not known.ble_address for known in self.api.bikes.values()):
                self.hass.async_create_task(self.async_request_refresh())
            return
        state = self.data.states.get(bike.unique_id)
        if state is None or state.in_range:
            return
        _LOGGER.debug("Bike %s came into range, refreshing", bike.frame_number)
        state.in_range = True
        self.async_update_listeners()
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        if not self.data:
            return
        bike = self._bike_for_address(service_info.address)
        if bike is None:
            return
        state = self.data.states.get(bike.unique_id)
        if state is None or not state.in_range:
            return
        _LOGGER.debug("Bike %s went out of range", bike.frame_number)
        state.in_range = False
        state.connection_state = "out_of_range"
        self.async_update_listeners()

    def _bike_for_address(self, address: str) -> VanMoofBike | None:
        for bike in self.api.bikes.values():
            if bike.ble_address and bike.ble_address.upper() == address.upper():
                return bike
        return None

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

            if bike.ble_address and not bluetooth.async_address_present(
                self.hass, bike.ble_address, connectable=False
            ):
                # Bike is away: do not connect, its next advertisement triggers a refresh
                states[bike.unique_id] = self._stale_state(
                    previous_state, connection_state="out_of_range"
                )
                continue

            try:
                async with self._lock_for(bike.unique_id):
                    state, address = await VanMoofBikeBleClient(
                        bike, self.hass
                    ).async_fetch_state()
                if address and bike.ble_address != address:
                    bike.ble_address = address
                    self._async_track_unavailable(bike)
                state.last_seen = dt_util.utcnow()
                state.carry_over(previous_state)
                states[bike.unique_id] = state
            except VanMoofBleError as err:
                states[bike.unique_id] = self._stale_state(
                    previous_state,
                    connection_state=_connection_state_for(err),
                    errors=str(err),
                )

        self.hass.async_create_task(self._async_persist_entry())
        return VanMoofCoordinatorData(
            bikes=dict(self.api.bikes), states=states
        )

    @staticmethod
    def _stale_state(
        previous_state: BikeState | None,
        *,
        connection_state: str,
        errors: str | None = None,
    ) -> BikeState:
        """Return the last known state, marked as not freshly fetched."""
        if previous_state is None or not previous_state.available:
            state = BikeState(
                available=False,
                in_range=False,
                connection_state=connection_state,
                errors=errors,
            )
            state.carry_over(previous_state)
            return state
        return replace(
            previous_state,
            in_range=connection_state != "out_of_range",
            connection_state=connection_state,
            errors=errors if errors is not None else previous_state.errors,
        )

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
            self._async_track_unavailable(bike)

        if state is not None and self.data is not None:
            previous = self.data.states.get(bike_id)
            state.last_seen = dt_util.utcnow()
            state.carry_over(previous)
            states = dict(self.data.states)
            states[bike_id] = state
            self.async_set_updated_data(
                VanMoofCoordinatorData(
                    bikes=dict(self.api.bikes), states=states
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
