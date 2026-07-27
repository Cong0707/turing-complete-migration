import struct
import unittest

from turing_complete_migration.legacy_v6 import (
    COM_CONSTANT,
    COM_CUSTOM,
    COM_LEVEL_INPUT_1_PIN,
    COM_LEVEL_OUTPUT_1_PIN,
    COM_NAND_BIT,
    COM_RAM,
    convert_circuit_bytes,
    parse_v15,
)
from turing_complete_migration.snappy import compress_raw


def string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("<H", len(data)) + data


def build_v6_custom_program() -> bytes:
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBIH", 0, 7, 12, 34, 1, 10_000_000, 0))
    raw.extend(string("rv64-like"))
    raw.extend(struct.pack("<hhBBH", 0, 0, 2, 0, 9))
    raw.extend(struct.pack("<H", 0))
    raw.extend(string("hub"))
    raw.extend(struct.pack("<q", 2))

    raw.extend(struct.pack("<HhhBq", 92, 10, 20, 1, 100))
    raw.extend(string("rv-unit"))
    raw.extend(struct.pack("<QQhqhh", 0, 0, 0, 1234, 2, -3))

    raw.extend(struct.pack("<HhhBq", 94, 40, 50, 0, 101))
    raw.extend(string("program"))
    raw.extend(struct.pack("<QQhHq", 512, 0, 1, 1, 86))
    raw.extend(string("new_program"))

    raw.extend(struct.pack("<qBB", 1, 0, 3))
    raw.extend(string("data"))
    raw.extend(struct.pack("<hhBB", 0, 0, 5, 0))
    return bytes([6]) + compress_raw(bytes(raw))


def build_direct_enum(version: int, *, teleport: bool = False) -> bytes:
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBQH", 0, 0, 1, 2, 1, 10_000_000, 0))
    raw.extend(string(f"version {version}"))
    raw.extend(struct.pack("<hhBH", 0, 0, 0, 0))
    raw.extend(struct.pack("<H", 0))
    raw.extend(string(""))
    raw.extend(struct.pack("<q", 1))
    raw.extend(struct.pack("<HhhBq", 2, 4, 5, 0, 99))
    raw.extend(string("on"))
    raw.extend(struct.pack("<Hq h q", 0, 0, 0, 1))
    if version == 7:
        raw.extend(struct.pack("<q", -1))
    else:
        raw.extend(struct.pack("<HH", 0, 0))
    raw.extend(struct.pack("<qB", 1, 4))
    raw.extend(string("wire"))
    raw.extend(struct.pack("<hh", 1, 2))
    if teleport:
        raw.extend(struct.pack("<Bhh", 0x20, 30, 40))
    else:
        raw.extend(struct.pack("<BB", (2 << 5) | 7, 0))
    return bytes([version]) + compress_raw(bytes(raw))


def build_intermediate_current(version: int) -> bytes:
    if version not in (13, 14):
        raise ValueError("fixture only supports versions 13 and 14")
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBQH", 0, 7, 12, 34, 1, 10_000_000, 1))
    raw.extend(struct.pack("<q", 456))
    raw.extend(string(f"version {version}"))
    raw.extend(struct.pack("<BHH", 2, 9, 3))
    raw.extend(b"abc")
    raw.extend(string("hub"))
    raw.extend(struct.pack("<q", 2))

    raw.extend(struct.pack("<HhhBq", COM_CONSTANT, 4, -5, 2, 99))
    raw.extend(string("0x2a"))
    raw.extend(struct.pack("<HQQqhqB", 2, 7, 8, -3, -2, 64, 1))
    if version == 14:
        raw.extend(struct.pack("<qq", 123, 456))
    raw.extend(struct.pack("<BBH", 1, 9, 1))
    raw.extend(struct.pack("<qq", 10, 20))
    raw.extend(string("link"))
    raw.extend(struct.pack("<qqH", 30, 40, 1))
    raw.extend(string("level"))
    raw.extend(string("program"))

    raw.extend(struct.pack("<HhhBq", COM_CUSTOM, -8, 6, 1, 100))
    raw.extend(string("custom label"))
    raw.extend(struct.pack("<HqhqB", 0, 0, 3, 8, 0))
    if version == 14:
        raw.extend(struct.pack("<qq", -1, 0))
    raw.extend(struct.pack("<BBHHqHqq", 0, 0, 0, 0, 1234, 1, 99, 16))

    raw.extend(struct.pack("<qB", 1, 5))
    raw.extend(string("wire"))
    raw.extend(struct.pack("<hhHHH", -1, 2, (3 << 13) | 12, (7 << 13) | 2, 0))
    return bytes([version]) + compress_raw(bytes(raw))


def build_v6_level_solution(*, save_id: int = 0, campaign_bound: bool = False) -> bytes:
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBIH", save_id, 0, 0, 0, 1, 10_000_000, 0))
    raw.extend(string("level solution"))
    raw.extend(struct.pack("<hhBBH", 0, 0, 0, campaign_bound, 0))
    raw.extend(struct.pack("<H", 0))
    raw.extend(string(""))
    raw.extend(struct.pack("<q", 3))
    for kind, x, permanent_id in ((240, -13, 1), (242, 13, 2), (7, 0, 3)):
        raw.extend(struct.pack("<HhhBq", kind, x, 0, 0, permanent_id))
        raw.extend(string(""))
        raw.extend(struct.pack("<QQh", 0, 0, 0))
    raw.extend(struct.pack("<qBB", 1, 0, 0))
    raw.extend(string(""))
    raw.extend(struct.pack("<hhBB", -13, 0, 13, 0))
    return bytes([6]) + compress_raw(bytes(raw))


class LegacyFormatTests(unittest.TestCase):
    def test_v6_custom_program_and_wire_convert_to_v15(self):
        converted, report = convert_circuit_bytes(build_v6_custom_program())
        parsed = parse_v15(converted)

        self.assertEqual(converted[0], 15)
        self.assertEqual(len(parsed.components), 2)
        self.assertEqual(len(parsed.wires), 1)
        custom = next(item for item in parsed.components if item.kind == COM_CUSTOM)
        program = next(item for item in parsed.components if item.kind == COM_RAM)
        self.assertEqual(custom.position, (27, 32))
        self.assertEqual(custom.custom_id, 1234)
        self.assertEqual(program.selected_programs, (("86", "new_program"),))
        self.assertEqual(parsed.wires[0].segments, ((0, 5),))
        self.assertEqual(report["source_component_count"], 2)
        self.assertEqual(report["output_component_count"], 2)

    def test_direct_enum_versions_convert_to_v15(self):
        for version in (7, 9, 10):
            with self.subTest(version=version):
                converted, report = convert_circuit_bytes(
                    build_direct_enum(version, teleport=version == 9)
                )
                parsed = parse_v15(converted)
                self.assertEqual(len(parsed.components), 1)
                self.assertEqual(len(parsed.wires), 1)
                self.assertEqual(report["source_version"], version)
                self.assertEqual(report["output_version"], 15)
                self.assertEqual(
                    report["teleport_wire_approximation_count"],
                    1 if version == 9 else 0,
                )
                if version == 9:
                    self.assertEqual(parsed.wires[0].segments, ((0, 1),))

    def test_v13_v14_convert_complete_current_fields_to_v15(self):
        for version in (13, 14):
            with self.subTest(version=version):
                converted, report = convert_circuit_bytes(
                    build_intermediate_current(version)
                )
                parsed = parse_v15(converted)

                self.assertEqual(report["source_version"], version)
                self.assertEqual(report["output_version"], 15)
                self.assertEqual(len(parsed.components), 2)
                constant, custom = parsed.components
                self.assertEqual(constant.kind, COM_CONSTANT)
                self.assertEqual(constant.user_label, "")
                self.assertEqual(constant.custom_string, "0x2a")
                self.assertEqual(constant.settings, (7, 8))
                self.assertTrue(constant.immutable)
                self.assertEqual(
                    (constant.cost_gate, constant.cost_delay),
                    (123, 456) if version == 14 else (-1, 0),
                )
                self.assertTrue(constant.little_endian)
                self.assertEqual(constant.init_data, 9)
                self.assertEqual(
                    constant.linked_components,
                    ((10, 20, "link", 30, 40),),
                )
                self.assertEqual(
                    constant.selected_programs,
                    (("level", "program"),),
                )
                self.assertEqual(custom.user_label, "custom label")
                self.assertEqual(custom.custom_string, "")
                self.assertEqual(custom.custom_id, 1234)
                self.assertEqual(custom.custom_word_sizes, ((99, 16),))
                self.assertEqual(len(parsed.wires), 1)
                self.assertEqual(parsed.wires[0].color, 5)
                self.assertEqual(parsed.wires[0].comment, "wire")
                self.assertEqual(parsed.wires[0].start, (-1, 2))
                self.assertEqual(parsed.wires[0].segments, ((3, 12), (7, 2)))

    def test_v6_campaign_interfaces_are_left_for_current_runtime_to_inject(self):
        converted, report = convert_circuit_bytes(build_v6_level_solution())
        parsed = parse_v15(converted)

        self.assertEqual([component.kind for component in parsed.components], [COM_NAND_BIT])
        self.assertEqual(len(parsed.wires), 1)
        self.assertEqual(report["source_component_count"], 3)
        self.assertEqual(report["output_component_count"], 1)
        self.assertEqual(report["runtime_component_count"], 3)
        self.assertEqual(report["stripped_level_interface_count"], 2)
        self.assertEqual(
            report["stripped_level_interface_kind_counts"],
            {COM_LEVEL_INPUT_1_PIN: 1, COM_LEVEL_OUTPUT_1_PIN: 1},
        )

    def test_v6_non_campaign_custom_definition_keeps_level_kinds_by_default(self):
        converted, report = convert_circuit_bytes(
            build_v6_level_solution(save_id=1234, campaign_bound=False)
        )
        parsed = parse_v15(converted)

        self.assertEqual(len(parsed.components), 3)
        self.assertEqual(report["stripped_level_interface_count"], 0)

    def test_v6_architecture_keeps_standalone_interfaces_by_default(self):
        converted, report = convert_circuit_bytes(
            build_v6_level_solution(save_id=1234, campaign_bound=True)
        )
        parsed = parse_v15(converted)

        self.assertEqual(len(parsed.components), 3)
        self.assertEqual(report["stripped_level_interface_count"], 0)

    def test_explicit_campaign_context_strips_architecture_copy_interfaces(self):
        converted, report = convert_circuit_bytes(
            build_v6_level_solution(save_id=1234, campaign_bound=True),
            strip_level_interfaces=True,
        )
        parsed = parse_v15(converted)

        self.assertEqual([component.kind for component in parsed.components], [COM_NAND_BIT])
        self.assertEqual(report["runtime_component_count"], 3)


if __name__ == "__main__":
    unittest.main()
