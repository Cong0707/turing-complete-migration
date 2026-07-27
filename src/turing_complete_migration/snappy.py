"""Small dependency-free codec for Turing Complete circuit containers.

Turing Complete's ``*.data`` schematic files use one version byte followed by
a raw Snappy stream.  This module deliberately exposes inspection only: it
does not pretend to understand or rewrite every game-specific structure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path


class SnappyDecodeError(ValueError):
    """Raised when a raw Snappy stream is malformed or truncated."""


MAX_DECOMPRESSED_SIZE = 256 * 1024 * 1024


def _read_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(10):
        if offset >= len(data):
            raise SnappyDecodeError("truncated Snappy length varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise SnappyDecodeError("Snappy length varint is too long")


def _write_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("Snappy varints cannot be negative")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def compress_raw(data: bytes) -> bytes:
    """Encode a standards-compliant raw Snappy stream using literals only.

    A literal-only stream is larger than an optimized Snappy stream, but it is
    deterministic, simple to audit, and fully compatible with the game's
    SuperSnappy decoder. Save files are small enough that compression ratio is
    not important for migration.
    """

    output = bytearray(_write_varint(len(data)))
    offset = 0
    while offset < len(data):
        length = min(len(data) - offset, 65536)
        length_code = length - 1
        if length < 60:
            output.append(length_code << 2)
        else:
            width = max(1, (length_code.bit_length() + 7) // 8)
            output.append((59 + width) << 2)
            output.extend(length_code.to_bytes(width, "little"))
        output.extend(data[offset : offset + length])
        offset += length
    return bytes(output)


def decompress_raw(data: bytes) -> bytes:
    """Decode a raw (not framed) Snappy stream."""

    expected, offset = _read_varint(data)
    if expected > MAX_DECOMPRESSED_SIZE:
        raise SnappyDecodeError(
            f"declared Snappy output length {expected} exceeds safety limit "
            f"{MAX_DECOMPRESSED_SIZE}"
        )
    output = bytearray()

    def copy_from_history(distance: int, length: int) -> None:
        if distance <= 0 or distance > len(output):
            raise SnappyDecodeError(
                f"invalid Snappy copy distance {distance} at output {len(output)}"
            )
        if len(output) + length > expected:
            raise SnappyDecodeError("Snappy copy exceeds declared output length")
        for _ in range(length):
            output.append(output[-distance])

    while len(output) < expected:
        if offset >= len(data):
            raise SnappyDecodeError("truncated Snappy tag stream")
        tag = data[offset]
        offset += 1
        tag_type = tag & 0x03

        if tag_type == 0:
            length_code = tag >> 2
            if length_code < 60:
                length = length_code + 1
            else:
                width = length_code - 59
                if offset + width > len(data):
                    raise SnappyDecodeError("truncated Snappy literal length")
                length = int.from_bytes(data[offset : offset + width], "little") + 1
                offset += width
            if offset + length > len(data):
                raise SnappyDecodeError("truncated Snappy literal")
            if len(output) + length > expected:
                raise SnappyDecodeError("Snappy literal exceeds declared output length")
            output.extend(data[offset : offset + length])
            offset += length
        elif tag_type == 1:
            if offset >= len(data):
                raise SnappyDecodeError("truncated Snappy COPY_1")
            length = 4 + ((tag >> 2) & 0x07)
            distance = ((tag & 0xE0) << 3) | data[offset]
            offset += 1
            copy_from_history(distance, length)
        elif tag_type == 2:
            if offset + 2 > len(data):
                raise SnappyDecodeError("truncated Snappy COPY_2")
            length = 1 + (tag >> 2)
            distance = int.from_bytes(data[offset : offset + 2], "little")
            offset += 2
            copy_from_history(distance, length)
        else:
            if offset + 4 > len(data):
                raise SnappyDecodeError("truncated Snappy COPY_4")
            length = 1 + (tag >> 2)
            distance = int.from_bytes(data[offset : offset + 4], "little")
            offset += 4
            copy_from_history(distance, length)

    if len(output) != expected:
        raise SnappyDecodeError(
            f"decoded length {len(output)} does not match declared length {expected}"
        )
    if offset != len(data):
        raise SnappyDecodeError(f"{len(data) - offset} trailing byte(s) after Snappy stream")
    return bytes(output)


@dataclass(frozen=True)
class CircuitInfo:
    path: str
    version: int | None
    compressed_size: int
    raw_size: int | None
    sha256: str
    valid: bool
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_circuit(path: Path, *, display_path: str | None = None) -> CircuitInfo:
    payload = path.read_bytes()
    digest = sha256(payload).hexdigest()
    shown = display_path or str(path)
    if not payload:
        return CircuitInfo(shown, None, 0, None, digest, False, "empty file")
    try:
        raw = decompress_raw(payload[1:])
    except (SnappyDecodeError, IndexError) as exc:
        return CircuitInfo(
            shown,
            payload[0],
            len(payload),
            None,
            digest,
            False,
            str(exc),
        )
    return CircuitInfo(shown, payload[0], len(payload), len(raw), digest, True)
