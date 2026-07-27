from pathlib import Path
import tempfile
import unittest

from turing_complete_migration.snappy import (
    MAX_DECOMPRESSED_SIZE,
    SnappyDecodeError,
    compress_raw,
    decompress_raw,
    inspect_circuit,
)


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def literal_stream(payload: bytes) -> bytes:
    length = len(payload)
    if length <= 60:
        tag = bytes([(length - 1) << 2])
    else:
        encoded = (length - 1).to_bytes(2, "little")
        tag = bytes([(59 + len(encoded)) << 2]) + encoded
    return varint(length) + tag + payload


class SnappyTests(unittest.TestCase):
    def test_literal_encoder_round_trip(self):
        for payload in (b"", b"hello", bytes(range(256)) * 300):
            self.assertEqual(decompress_raw(compress_raw(payload)), payload)

    def test_literal(self):
        self.assertEqual(decompress_raw(literal_stream(b"hello")), b"hello")

    def test_copy_one(self):
        # "abcd" literal followed by COPY_1(distance=4, length=4).
        stream = varint(8) + bytes([(4 - 1) << 2]) + b"abcd" + bytes([0x01, 0x04])
        self.assertEqual(decompress_raw(stream), b"abcdabcd")

    def test_inspect_container(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "circuit.data"
            path.write_bytes(bytes([6]) + literal_stream(b"payload"))
            info = inspect_circuit(path)
            self.assertTrue(info.valid)
            self.assertEqual(info.version, 6)
            self.assertEqual(info.raw_size, 7)

    def test_rejects_unreasonably_large_declared_output(self):
        with self.assertRaises(SnappyDecodeError):
            decompress_raw(varint(MAX_DECOMPRESSED_SIZE + 1))


if __name__ == "__main__":
    unittest.main()
