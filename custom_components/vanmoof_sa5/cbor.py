"""Minimal CBOR helpers for the VanMoof SA5 protocol."""

from __future__ import annotations

from collections.abc import Iterable


def encode_cbor(value: object) -> bytes:
    """Encode the small set of CBOR types used by VanMoof."""
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"

    if isinstance(value, int):
        if value < 0:
            raise ValueError("Negative integers are not supported")
        if value < 24:
            return bytes([value])
        if value < 256:
            return bytes([0x18, value])
        if value < 65536:
            return bytes([0x19, (value >> 8) & 0xFF, value & 0xFF])
        return bytes(
            [
                0x1A,
                (value >> 24) & 0xFF,
                (value >> 16) & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )

    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return _encode_bytes_like(encoded, 0x60, 0x78)

    if isinstance(value, (bytes, bytearray)):
        return _encode_bytes_like(bytes(value), 0x40, 0x58)

    if isinstance(value, Iterable):
        items = [encode_cbor(item) for item in value]
        if len(items) >= 24:
            raise ValueError("Large arrays are not supported")
        return bytes([0x80 + len(items)]) + b"".join(items)

    raise ValueError(f"Unsupported CBOR type: {type(value)!r}")


def _encode_bytes_like(data: bytes, short_prefix: int, long_prefix: int) -> bytes:
    if len(data) < 24:
        return bytes([short_prefix + len(data)]) + data
    if len(data) < 256:
        return bytes([long_prefix, len(data)]) + data
    raise ValueError("Large payloads are not supported")


def decode_cbor(buf: bytes, offset: int = 0) -> tuple[object | None, int]:
    """Decode the small CBOR subset used by VanMoof."""
    if len(buf) <= offset:
        return None, 0

    initial = buf[offset]
    major = (initial >> 5) & 0x07
    additional = initial & 0x1F

    if additional < 24:
        value = additional
        header_size = 1
    elif additional == 24:
        value = buf[offset + 1]
        header_size = 2
    elif additional == 25:
        value = int.from_bytes(buf[offset + 1 : offset + 3], "big")
        header_size = 3
    elif additional == 26:
        value = int.from_bytes(buf[offset + 1 : offset + 5], "big")
        header_size = 5
    elif additional == 31:
        if major == 4:
            return _decode_indefinite_array(buf, offset)
        if major == 5:
            return _decode_indefinite_map(buf, offset)
        return None, 1
    else:
        return None, len(buf) - offset

    if major == 0:
        return value, header_size
    if major == 1:
        return -1 - value, header_size
    if major == 2:
        start = offset + header_size
        end = start + value
        return buf[start:end], header_size + value
    if major == 3:
        start = offset + header_size
        end = start + value
        return buf[start:end].decode("utf-8"), header_size + value
    if major == 4:
        items: list[object] = []
        pos = offset + header_size
        for _ in range(value):
            item, size = decode_cbor(buf, pos)
            items.append(item)
            pos += size
        return items, pos - offset
    if major == 5:
        mapping: dict[object, object] = {}
        pos = offset + header_size
        for _ in range(value):
            key, key_size = decode_cbor(buf, pos)
            pos += key_size
            item, item_size = decode_cbor(buf, pos)
            pos += item_size
            mapping[key] = item
        return mapping, pos - offset
    if major == 7:
        if additional == 20:
            return False, 1
        if additional == 21:
            return True, 1
        if additional == 22:
            return None, 1
        if additional == 26:
            import struct

            return struct.unpack(">f", buf[offset + 1 : offset + 5])[0], 5
        return value, header_size

    return None, header_size


def _decode_indefinite_map(buf: bytes, offset: int) -> tuple[dict[object, object], int]:
    mapping: dict[object, object] = {}
    pos = offset + 1
    while pos < len(buf) and buf[pos] != 0xFF:
        key, key_size = decode_cbor(buf, pos)
        pos += key_size
        value, value_size = decode_cbor(buf, pos)
        pos += value_size
        mapping[key] = value
    if pos < len(buf):
        pos += 1
    return mapping, pos - offset


def _decode_indefinite_array(buf: bytes, offset: int) -> tuple[list[object], int]:
    items: list[object] = []
    pos = offset + 1
    while pos < len(buf) and buf[pos] != 0xFF:
        item, size = decode_cbor(buf, pos)
        items.append(item)
        pos += size
    if pos < len(buf):
        pos += 1
    return items, pos - offset
