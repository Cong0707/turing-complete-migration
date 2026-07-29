from pathlib import Path
import re
import unittest


SPEC_PATH = Path(__file__).parents[1] / "examples" / "rv64i" / "spec.isa"
EXPECTED_OPCODES = {
    "0000011",  # LOAD
    "0010011",  # OP-IMM
    "0010111",  # AUIPC
    "0011011",  # OP-IMM-32
    "0100011",  # STORE
    "0110011",  # OP
    "0110111",  # LUI
    "0111011",  # OP-32
    "1100011",  # BRANCH
    "1100111",  # JALR
    "1101111",  # JAL
    "1110011",  # SYSTEM
}


def register_encoding(source: str, name: str) -> int:
    fields_source = source.split("[fields]", 1)[1].split("[instructions]", 1)[0]
    match = re.search(rf"(?m)^{re.escape(name)}\s+([01]{{5}})\s*$", fields_source)
    if match is None:
        raise AssertionError(f"register {name!r} is missing from spec.isa")
    return int(match.group(1), 2)


def encode_lui_from_definition(source: str, dest: str, immediate: int) -> bytes:
    instruction_source = source.split("[instructions]", 1)[1]
    match = re.search(
        r"(?m)^lui\s+%dest\(register\)\s+,\s+%imm:S64\(immediate\)\s*$\n"
        r"^%imm\[19:0\]\s+%dest\[4:0\]\s+0110111\s*$",
        instruction_source,
    )
    if match is None:
        raise AssertionError("unexpected LUI definition in spec.isa")
    word = ((immediate & 0xFFFFF) << 12) | (register_encoding(source, dest) << 7) | 0x37
    return word.to_bytes(4, "little")


def instruction_patterns(source: str) -> list[tuple[str, int]]:
    instruction_source = source.split("[instructions]", 1)[1]
    patterns: list[tuple[str, int]] = []
    fixed = re.compile(r"[01?]+")
    sliced = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*\[(\d+):(\d+)\]")

    for block in re.split(r"\n\s*\n", instruction_source.strip()):
        block_patterns: list[tuple[str, int]] = []
        for line in block.splitlines():
            tokens = line.strip().split()
            if not tokens:
                continue
            width = 0
            for token in tokens:
                if fixed.fullmatch(token):
                    width += len(token)
                    continue
                match = sliced.fullmatch(token)
                if match:
                    top, bottom = map(int, match.groups())
                    width += top - bottom + 1
                    continue
                break
            else:
                block_patterns.append((tokens[-1][-7:], width))
        if len(block_patterns) != 1:
            raise AssertionError(
                f"expected one output pattern in instruction block, got {block_patterns}:\n{block}"
            )
        patterns.extend(block_patterns)
    return patterns


class Rv64iSpecTests(unittest.TestCase):
    def test_uses_little_endian_and_only_expected_opcodes(self):
        source = SPEC_PATH.read_text("utf-8")
        self.assertIn("endianness = little", source)
        self.assertIn('line_comments = [";", "//", "#"]', source)
        opcodes = {opcode for opcode, _ in instruction_patterns(source)}
        self.assertEqual(opcodes, EXPECTED_OPCODES)
        self.assertNotIn("0001111", opcodes)

    def test_every_definition_emits_one_32_bit_instruction(self):
        source = SPEC_PATH.read_text("utf-8")
        patterns = instruction_patterns(source)
        self.assertGreaterEqual(len(patterns), 39)
        self.assertTrue(all(width == 32 for _, width in patterns))

    def test_lui_encodes_upper_immediate_in_little_endian_order(self):
        source = SPEC_PATH.read_text("utf-8")
        cases = {
            ("x0", 0x00000): bytes.fromhex("37 00 00 00"),
            ("a0", 0x12345): bytes.fromhex("37 55 34 12"),
            ("x15", 0x76543): bytes.fromhex("b7 37 54 76"),
            ("x31", 0xFFFFF): bytes.fromhex("b7 ff ff ff"),
        }
        for (dest, immediate), expected in cases.items():
            with self.subTest(dest=dest, immediate=hex(immediate)):
                self.assertEqual(
                    encode_lui_from_definition(source, dest, immediate), expected
                )


if __name__ == "__main__":
    unittest.main()
