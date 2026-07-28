from contextlib import redirect_stderr
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
TOOLCHAIN_DIR = ROOT / "examples" / "rv64i" / "c-toolchain"
MODULE_PATH = TOOLCHAIN_DIR / "compile.py"

module_spec = spec_from_file_location("tc_rv64i_compile", MODULE_PATH)
assert module_spec is not None and module_spec.loader is not None
compile_rv64 = module_from_spec(module_spec)
sys.modules[module_spec.name] = compile_rv64
module_spec.loader.exec_module(compile_rv64)


def make_instructions(words: list[int]) -> list[compile_rv64.Instruction]:
    return [
        compile_rv64.Instruction(index * 4, word, f"word_{index}")
        for index, word in enumerate(words)
    ]


class Rv64iCompileTests(unittest.TestCase):
    def test_parses_original_objdump_shape(self):
        dump = """
0000000000000000 <_start>:
   0:   7ff00113                addi    sp,zero,2047
   4:   08000093                addi    ra,zero,128
"""
        instructions = compile_rv64.parse_objdump(dump)
        self.assertEqual([item.address for item in instructions], [0, 4])
        self.assertEqual(instructions[0].word, 0x7FF00113)
        self.assertEqual(instructions[0].text, "addi    sp,zero,2047")

    def test_rejects_non_32_bit_objdump_instruction(self):
        dump = "   0:   0001                    c.nop\n"
        with self.assertRaisesRegex(compile_rv64.CompileError, "非 32 位"):
            compile_rv64.parse_objdump(dump)

    def test_layout_requires_ttext_zero(self):
        instructions = [compile_rv64.Instruction(4, 0x00000013, "nop")]
        with self.assertRaisesRegex(compile_rv64.CompileError, "不是.*预期的 0"):
            compile_rv64.validate_layout(instructions)

    def test_layout_rejects_address_gaps(self):
        instructions = [
            compile_rv64.Instruction(0, 0x00000013, "nop"),
            compile_rv64.Instruction(8, 0x00000013, "nop"),
        ]
        with self.assertRaisesRegex(compile_rv64.CompileError, "地址不连续"):
            compile_rv64.validate_layout(instructions)

    def test_accepts_all_cpu_opcode_groups(self):
        words = {
            "LOAD": 0x00003003,
            "OP-IMM": 0x00000013,
            "AUIPC": 0x00000017,
            "OP-IMM-32": 0x0000001B,
            "STORE": 0x00003023,
            "OP": 0x00000033,
            "LUI": 0x00000037,
            "OP-32": 0x0000003B,
            "BRANCH": 0x00000063,
            "JALR": 0x00000067,
            "JAL": 0x0000006F,
            "SYSTEM": 0x00000073,
        }
        for name, word in words.items():
            with self.subTest(name=name):
                self.assertIsNone(compile_rv64.validate_rv64i_word(word))

    def test_rejects_extensions_not_in_cpu(self):
        rejected = {
            "MUL": 0x02000033,
            "FENCE": 0x0000000F,
            "CSRRW": 0x00101073,
            "unknown": 0xFFFFFFFF,
        }
        for name, word in rejected.items():
            with self.subTest(name=name):
                self.assertIsNotNone(compile_rv64.validate_rv64i_word(word))

    def test_rejects_invalid_shift_funct(self):
        invalid_slli = (0b000001 << 26) | (1 << 20) | (1 << 12) | 0x13
        invalid_slliw = (0b0000001 << 25) | (1 << 20) | (1 << 12) | 0x1B
        self.assertIsNotNone(compile_rv64.validate_rv64i_word(invalid_slli))
        self.assertIsNotNone(compile_rv64.validate_rv64i_word(invalid_slliw))

    def test_decodes_all_supported_groups_to_real_mnemonics(self):
        words = [
            0x00003003,
            0x00000013,
            0x00000017,
            0x0000001B,
            0x00003023,
            0x00000033,
            0x00000037,
            0x0000003B,
            0x00000063,
            0x00000067,
            0x0000006F,
            0x00000073,
        ]
        instructions = make_instructions(words)
        labels = compile_rv64.collect_labels(instructions)
        mnemonics = [
            compile_rv64.decode_instruction(item, labels).split()[0]
            for item in instructions
        ]
        self.assertEqual(
            mnemonics,
            [
                "ld",
                "addi",
                "auipc",
                "addiw",
                "sd",
                "add",
                "lui",
                "addw",
                "beq",
                "jalr",
                "jal",
                "ecall",
            ],
        )

    def test_rebuilds_branch_and_jal_labels(self):
        instructions = make_instructions([0x0080006F, 0x00000013, 0x00000013])
        rendered = compile_rv64.render_asm(instructions, "temp.elf")
        self.assertIn("jal x0, loc_00000008", rendered)
        self.assertIn("loc_00000008:", rendered)

    def test_rejects_jump_target_missing_from_objdump(self):
        instructions = make_instructions([0x0080006F])
        with self.assertRaisesRegex(compile_rv64.CompileError, "不是 objdump"):
            compile_rv64.collect_labels(instructions)

    def test_rendered_output_is_direct_asm_not_binary_data(self):
        instructions = make_instructions([0x00C58533, 0x00000013])
        rendered = compile_rv64.render_asm(instructions, "temp.elf")
        self.assertIn("start:", rendered)
        self.assertIn("add x10, x11, x12", rendered)
        self.assertNotIn("U32", rendered)
        self.assertNotIn("0b000", rendered)

    def test_main_writes_asm_from_existing_elf(self):
        dump = """
   0:   7ff00113                addi    sp,zero,2047
   4:   0000006f                j       4
"""
        with tempfile.TemporaryDirectory() as directory:
            elf = Path(directory) / "temp.elf"
            output = Path(directory) / "test.asm"
            elf.write_bytes(b"ELF")
            with patch.object(compile_rv64, "run_objdump", return_value=dump):
                with redirect_stderr(StringIO()):
                    result = compile_rv64.main([str(elf), "-o", str(output)])
            rendered = output.read_text("utf-8")
        self.assertEqual(result, 0)
        self.assertIn("addi x2, x0, 2047", rendered)
        self.assertIn("jal x0, loc_00000004", rendered)

    def test_run_sh_preserves_original_gcc_command(self):
        source = (TOOLCHAIN_DIR / "run.sh").read_text("utf-8")
        for text in (
            'SRC="$1"',
            "ELF=temp.elf",
            "riscv64-unknown-elf-gcc",
            "-march=rv64i -mabi=lp64",
            "-ffreestanding -nostdlib -lgcc -O0",
            "-fno-stack-protector",
            "-fomit-frame-pointer",
            "-Wl,-Ttext=0",
            "-fno-pic -fno-pie",
            '"$SCRIPT_DIR/_start.S"',
            '"$SRC" -o "$ELF"',
            "compile.py",
        ):
            self.assertIn(text, source)

    def test_startup_matches_user_original(self):
        source = (TOOLCHAIN_DIR / "_start.S").read_text("utf-8")
        self.assertIn("addi sp, x0, 2047", source)
        self.assertIn("addi x1, x0, 128", source)
        self.assertIn("jal ra, main", source)
        self.assertIn("j end", source)


if __name__ == "__main__":
    unittest.main()
