"""BLE transport for VanMoof SA5/A5 bikes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    APP_CHAR_UUID,
    DEFAULT_SCAN_SECONDS,
    SERVICE_UUID,
    SERVICE_UUID_NODASH,
    WRITE_CHAR_UUID,
)
from .models import BikeState, VanMoofBike
from .protocol import (
    ALL_TOPICS,
    Topic,
    AuthMessage,
    ChallengeMessage,
    FragmentReassembler,
    TopicMessage,
    build_certificate_message,
    build_fragments,
    build_subscribe_message,
    sign_challenge,
)

_LOGGER = logging.getLogger(__name__)


class VanMoofBleError(Exception):
    """Raised when BLE communication fails."""


class VanMoofBikeBleClient:
    """Connect to a single VanMoof bike over BLE."""

    def __init__(self, bike: VanMoofBike) -> None:
        self._bike = bike

    async def async_fetch_state(self) -> tuple[BikeState, str | None]:
        """Try all candidate advertisements until one authenticates."""
        candidates = await self._async_discover_candidates()
        if not candidates:
            raise VanMoofBleError("No nearby VanMoof BLE advertisements were found")

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                state = await self._async_read_candidate(candidate)
                return state, candidate.address
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.debug(
                    "Candidate %s did not match bike %s",
                    candidate.address,
                    self._bike.frame_number,
                    exc_info=True,
                )

        raise VanMoofBleError(
            f"Could not authenticate to bike {self._bike.frame_number}: {last_error}"
        )

    async def async_execute_raw_command(self, command_hex: str) -> str | None:
        """Authenticate and send a raw SA5 command."""
        candidates = await self._async_discover_candidates()
        if not candidates:
            raise VanMoofBleError("No nearby VanMoof BLE advertisements were found")

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                await self._async_send_command_to_candidate(candidate, command_hex)
                return candidate.address
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.debug(
                    "Command candidate %s did not match bike %s",
                    candidate.address,
                    self._bike.frame_number,
                    exc_info=True,
                )

        raise VanMoofBleError(
            f"Could not send command to bike {self._bike.frame_number}: {last_error}"
        )

    async def _async_discover_candidates(self) -> list[BLEDevice]:
        discovered = await BleakScanner.discover(
            timeout=DEFAULT_SCAN_SECONDS,
            return_adv=True,
        )

        matched: list[BLEDevice] = []
        stored: BLEDevice | None = None
        for _, (device, advertisement) in discovered.items():
            name = ((advertisement.local_name or device.name) or "").lower()
            services = {service.lower() for service in advertisement.service_uuids or []}
            is_vanmoof = (
                "vanmoof" in name
                or name.startswith("xs4-")
                or SERVICE_UUID.lower() in services
                or SERVICE_UUID_NODASH.lower() in services
            )
            if not is_vanmoof:
                continue
            if self._bike.ble_address and device.address.lower() == self._bike.ble_address.lower():
                stored = device
            else:
                matched.append(device)

        if stored:
            return [stored, *matched]
        return matched

    async def _async_read_candidate(self, device: BLEDevice) -> BikeState:
        if not self._bike.certificate or not self._bike.private_key:
            raise VanMoofBleError("Missing certificate or private key for bike")

        queue: asyncio.Queue[Any] = asyncio.Queue()
        reassembler = FragmentReassembler()

        def notification_handler(_: int, payload: bytearray) -> None:
            message = reassembler.feed(bytes(payload))
            if message is not None:
                queue.put_nowait(message)

        client = await establish_connection(
            BleakClient, device, device.name or device.address
        )
        try:
            write_uuid = await self._async_authenticate_connection(
                client, queue, notification_handler
            )
            await self._async_write_fragments(
                client, write_uuid, build_subscribe_message(ALL_TOPICS)
            )
            topics = await self._async_collect_topics(queue, duration=5.0)
        finally:
            await client.disconnect()

        if Topic.BATTERY_LEVEL not in topics and Topic.LOCK_STATE not in topics:
            raise VanMoofBleError("Bike connected but did not return the expected topics")

        return BikeState(
            available=True,
            in_range=True,
            battery_level=_coerce_int(topics.get(Topic.BATTERY_LEVEL)),
            module_battery=_coerce_int(topics.get(Topic.MODULE_BATTERY)),
            locked=_map_locked(topics.get(Topic.LOCK_STATE)),
            distance_km=_map_distance(topics.get(Topic.DISTANCE)),
            power_level=_map_power(topics.get(Topic.POWER_LEVEL)),
            light_mode=_map_light(topics.get(Topic.LIGHT_MODE)),
            speed_limit=_map_speed_limit(topics.get(97)),
            connection_state="connected",
            firmware_info=_stringify_value(topics.get(Topic.FW_INFO)),
            errors=_stringify_value(topics.get(Topic.ERRORS)),
            raw_topics=topics,
        )

    async def _async_send_command_to_candidate(
        self, device: BLEDevice, command_hex: str
    ) -> None:
        if not self._bike.certificate or not self._bike.private_key:
            raise VanMoofBleError("Missing certificate or private key for bike")

        queue: asyncio.Queue[Any] = asyncio.Queue()
        reassembler = FragmentReassembler()

        def notification_handler(_: int, payload: bytearray) -> None:
            message = reassembler.feed(bytes(payload))
            if message is not None:
                queue.put_nowait(message)

        client = await establish_connection(
            BleakClient, device, device.name or device.address
        )
        try:
            write_uuid = await self._async_authenticate_connection(
                client, queue, notification_handler
            )
            await client.write_gatt_char(write_uuid, bytes.fromhex(command_hex), response=False)
            await asyncio.sleep(0.5)
        finally:
            await client.disconnect()

    async def _async_authenticate_connection(
        self,
        client: BleakClient,
        queue: asyncio.Queue[Any],
        notification_handler,
    ) -> str:
        await client.start_notify(APP_CHAR_UUID, notification_handler)
        write_uuid = await self._async_resolve_write_uuid(client)
        await asyncio.sleep(1.5)

        await self._async_write_fragments(
            client, write_uuid, build_certificate_message(self._bike.certificate)
        )
        challenge = await self._async_wait_for(queue, ChallengeMessage, timeout=6.0)

        await self._async_write_fragments(
            client, write_uuid, sign_challenge(challenge.nonce, self._bike.private_key)
        )
        auth = await self._async_wait_for(queue, AuthMessage, timeout=10.0)
        if not auth.authenticated:
            raise VanMoofBleError("Bike rejected the certificate for this advertisement")

        await asyncio.sleep(0.5)
        return write_uuid

    async def _async_resolve_write_uuid(self, client: BleakClient) -> str:
        with contextlib.suppress(Exception):
            services = await client.get_services()
            for service in services:
                for characteristic in service.characteristics:
                    if characteristic.uuid.lower() == WRITE_CHAR_UUID.lower():
                        return WRITE_CHAR_UUID
        return APP_CHAR_UUID

    async def _async_write_fragments(
        self, client: BleakClient, write_uuid: str, payload: bytes
    ) -> None:
        for fragment in build_fragments(payload):
            await client.write_gatt_char(write_uuid, fragment, response=False)

    async def _async_wait_for(
        self,
        queue: asyncio.Queue[Any],
        message_type: type[Any],
        *,
        timeout: float,
    ) -> Any:
        end = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = end - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise VanMoofBleError(f"Timed out waiting for {message_type.__name__}")
            message = await asyncio.wait_for(queue.get(), timeout=remaining)
            if isinstance(message, message_type):
                return message

    async def _async_collect_topics(
        self, queue: asyncio.Queue[Any], *, duration: float
    ) -> dict[int, Any]:
        topics: dict[int, Any] = {}
        end = asyncio.get_running_loop().time() + duration
        while True:
            remaining = end - asyncio.get_running_loop().time()
            if remaining <= 0:
                return topics
            try:
                message = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return topics
            if isinstance(message, TopicMessage):
                topics[message.topic] = message.value


def _coerce_int(value: object | None) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _map_locked(value: object | None) -> bool | None:
    if not isinstance(value, int):
        return None
    return value != 3


def _map_distance(value: object | None) -> float | None:
    if not isinstance(value, int | float):
        return None
    return round((float(value) / 100.0), 1)


def _map_power(value: object | None) -> str | None:
    if isinstance(value, int):
        return str(value)
    return None


def _map_light(value: object | None) -> str | None:
    if value == 0:
        return "off"
    if value == 1:
        return "on"
    if value == 2:
        return "halo"
    if value == 3:
        return "auto"
    return None


def _map_speed_limit(value: object | None) -> str | None:
    if value == 0:
        return "25 km/h"
    if value == 1:
        return "32 km/h"
    if value == 2:
        return "24 km/h"
    return None


def _stringify_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)
