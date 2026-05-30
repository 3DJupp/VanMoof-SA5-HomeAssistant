"""VanMoof SA5 BLE protocol helpers."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import IntEnum

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .cbor import decode_cbor, encode_cbor


class PayloadType(IntEnum):
    """VanMoof payload types."""

    TOPIC_CBOR = 1
    SUBSCRIBE = 2
    AUTH_CERT = 3
    AUTH_CHALLENGE = 4
    AUTH_DETAILS = 5
    MTU_UPDATE = 6
    PARAM_UPDATE = 7


class Topic(IntEnum):
    """Topics exposed by the VanMoof bike."""

    LOCK_STATE = 1
    MODULE_BATTERY = 16
    BATTERY_LEVEL = 24
    CALORIES = 73
    SPEED = 80
    GEAR = 97
    POWER_LEVEL = 101
    LIGHT_MODE = 106
    ALARM = 110
    BELL_SOUND = 114
    BACKUP_CODE = 116
    LOCK_STATE_ALT = 161
    DISTANCE = 165
    FW_INFO = 192
    FIND_MY = 225
    ERRORS = 255
    SUBSCRIBE_CONTROL = 0xE001


TOPIC_NAMES: dict[int, str] = {
    Topic.LOCK_STATE: "lock_state",
    Topic.MODULE_BATTERY: "module_battery",
    Topic.BATTERY_LEVEL: "battery_level",
    Topic.CALORIES: "calories",
    Topic.SPEED: "speed",
    Topic.GEAR: "gear",
    Topic.POWER_LEVEL: "power_level",
    Topic.LIGHT_MODE: "light_mode",
    Topic.ALARM: "alarm",
    Topic.BELL_SOUND: "bell_sound",
    Topic.LOCK_STATE_ALT: "lock_state_alt",
    Topic.DISTANCE: "distance",
    Topic.FW_INFO: "fw_info",
    Topic.FIND_MY: "find_my",
    Topic.ERRORS: "errors",
}

ALL_TOPICS: list[int] = [
    Topic.LOCK_STATE,
    Topic.BATTERY_LEVEL,
    Topic.LOCK_STATE_ALT,
    Topic.POWER_LEVEL,
    Topic.LIGHT_MODE,
    Topic.DISTANCE,
    Topic.FW_INFO,
    Topic.ERRORS,
    Topic.CALORIES,
    Topic.FIND_MY,
    Topic.ALARM,
    Topic.BELL_SOUND,
    Topic.SPEED,
    Topic.GEAR,
    Topic.MODULE_BATTERY,
]


@dataclass(slots=True)
class TopicMessage:
    """Decoded topic message."""

    topic: int
    topic_name: str
    value: object | None


@dataclass(slots=True)
class AuthMessage:
    """Decoded auth message."""

    authenticated: bool
    encrypted: bool


@dataclass(slots=True)
class ChallengeMessage:
    """Decoded challenge message."""

    nonce: bytes


@dataclass(slots=True)
class ParamMessage:
    """Decoded param message."""

    data: object | None


S5Message = TopicMessage | AuthMessage | ChallengeMessage | ParamMessage


def build_fragments(payload: bytes, mtu: int = 244) -> list[bytes]:
    """Split a payload into BLE fragments."""
    chunk_size = mtu - 3
    fragments: list[bytes] = []
    offset = 0
    index = 0

    while offset < len(payload):
        chunk = payload[offset : offset + chunk_size]
        remaining = len(payload) - 1 if index == 0 else len(payload) - (chunk_size * index)
        header = bytes(
            [
                (0x80 if index == 0 else 0x00) | 1,
                (remaining >> 8) & 0xFF,
                remaining & 0xFF,
            ]
        )
        fragments.append(header + chunk)
        offset += chunk_size
        index += 1

    return fragments


def build_certificate_message(certificate_b64: str) -> bytes:
    """Build the AUTH_CERT message."""
    return bytes([PayloadType.AUTH_CERT]) + base64.b64decode(certificate_b64)


def sign_challenge(challenge: bytes, private_key_b64: str) -> bytes:
    """Sign a challenge with the VanMoof Ed25519 key."""
    private_bytes = base64.b64decode(private_key_b64)
    if len(private_bytes) >= 32:
        private_bytes = private_bytes[:32]
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    signature = private_key.sign(challenge)
    return bytes([PayloadType.AUTH_CHALLENGE]) + signature


def build_param_update_message(topic: Topic, value: int) -> bytes:
    """Build a PARAM_UPDATE message to set a topic value on the bike."""
    topic_bytes = int(topic).to_bytes(2, "big")
    return bytes([PayloadType.PARAM_UPDATE]) + topic_bytes + encode_cbor(value)


def build_subscribe_message(topics: list[int]) -> bytes:
    """Build the topic subscription message."""
    control_topic = Topic.SUBSCRIBE_CONTROL.to_bytes(2, "big")
    topic_bytes = b"".join(int(topic).to_bytes(2, "big") for topic in topics)
    return bytes([PayloadType.SUBSCRIBE]) + control_topic + topic_bytes


def parse_message(data: bytes) -> S5Message | None:
    """Parse a reassembled payload."""
    if not data:
        return None

    payload_type = data[0]
    rest = data[1:]

    if payload_type == PayloadType.AUTH_DETAILS:
        info, _ = decode_cbor(rest)
        if isinstance(info, dict):
            return AuthMessage(
                authenticated=bool(info.get("auth", False)),
                encrypted=bool(info.get("enc", False)),
            )
        return AuthMessage(authenticated=False, encrypted=False)

    if payload_type == PayloadType.AUTH_CHALLENGE:
        return ChallengeMessage(nonce=rest)

    if payload_type == PayloadType.PARAM_UPDATE:
        decoded, _ = decode_cbor(rest)
        return ParamMessage(data=decoded)

    if payload_type == PayloadType.TOPIC_CBOR:
        if len(rest) < 2:
            return None
        topic = int.from_bytes(rest[:2], "big")
        value: object | None = None
        if len(rest) > 2:
            value, _ = decode_cbor(rest, 2)
        return TopicMessage(
            topic=topic,
            topic_name=TOPIC_NAMES.get(topic, f"topic_{topic}"),
            value=value,
        )

    return None


class FragmentReassembler:
    """Reassemble VanMoof BLE fragments."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._total_len = 0

    def feed(self, data: bytes) -> S5Message | None:
        """Feed one fragment and return a full message if complete."""
        is_first = bool(data[0] & 0x80)
        total_len = int.from_bytes(data[1:3], "big")
        payload = data[3:]

        if is_first:
            self._buffer = bytearray(payload)
            self._total_len = total_len
        else:
            self._buffer.extend(payload)

        if len(self._buffer) >= self._total_len + 1:
            message = bytes(self._buffer[: self._total_len + 1])
            self._buffer = bytearray()
            return parse_message(message)

        return None
