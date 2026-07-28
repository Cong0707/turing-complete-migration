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
MODULE_PATH = TOOLCHAIN_DIR / "compile_c.py"

module_spec = spec_from_file_location("tc_rv64i_compile", MODULE_PATH)
assert module_spec is not None and module_spec.loader is not None
compile_c = module_from_spec(module_spec)
sys.modules[module_spec.name] = compile_c
module_spec.loader.exec_module(compile_c)


class Rv64iCompileTests(unittest.TestCase):
    def test_accepts_every_supported_opcode_group(self):
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
                self.assertIsNone(compile_c.validate_rv64i_word(word))

    def test_rejects_extensions_and_unimplemented_system_operations(self):
        rejected = {
            "MUL": 0x02000033,
            "FENCE": 0x0000000F,
            "CSRRW": 0x00101073,
            "unknown": 0xFFFFFFFF,
        }
        for name, word in rejected.items():
            with self.subTest(name=name):
                self.assertIsNotNone(compile_c.validate_rv64i_word(word))

    def test_rejects_invalid_shift_encodings(self):
        invalid_slli = (0b000001 << 26) | (1 << 20) | (1 << 12) | 0x13
        invalid_slliw = (0b0000001 << 25) | (1 << 20) | (1 << 12) | 0x1B
        self.assertIsNotNone(compile_c.validate_rv64i_word(invalid_slli))
        self.assertIsNotNone(compile_c.validate_rv64i_word(invalid_slliw))

    def test_binary_words_are_little_endian(self):
        data = bytes.fromhex("33 85 c5 00 13 00 00 00")
        self.assertEqual(
            compile_c.words_from_binary(data),
            [0x00C58533, 0x00000013],
        )

    def test_rejects_empty_or_non_32_bit_text(self):
        for data in (b"", b"\x13\x00"):
            with self.subTest(length=len(data)):
                with self.assertRaises(compile_c.CompileError):
                    compile_c.words_from_binary(data)

    def test_parses_objdump_and_renders_real_asm(self):
        dump = """
0000000000000000 <_start>:
   0:   00c58533                add x10,x11,x12
   4:   00000013                addi x0,x0,0
"""
        disassembly = compile_c.parse_objdump(dump)
        rendered = compile_c.render_tc_asm(
            [0x00C58533, 0x00000013],
            disassembly,
            source_names=["example.c"],
            stack_top=2032,
        )
        self.assertIn("start:", rendered)
        self.assertIn("add x10, x11, x12", rendered)
        self.assertIn("addi x0, x0, 0", rendered)
        self.assertNotIn("U32", rendered)

    def test_decodes_every_supported_opcode_group_to_mnemonics(self):
        words = [
            0x00003003,  # ld x0, 0(x0)
            0x00000013,  # addi x0, x0, 0
            0x00000017,  # auipc x0, 0
            0x0000001B,  # addiw x0, x0, 0
            0x00003023,  # sd x0, 0(x0)
            0x00000033,  # add x0, x0, x0
            0x00000037,  # lui x0, 0
            0x0000003B,  # addw x0, x0, x0
            0x00000063,  # beq x0, x0, current address
            0x00000067,  # jalr x0, 0(x0)
            0x0000006F,  # jal x0, current address
            0x00000073,  # ecall
        ]
        labels = compile_c.collect_labels(words)
        mnemonics = [
            compile_c.decode_rv64i_word(word, index * 4, labels).split()[0]
            for index, word in enumerate(words)
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

    def test_rebuilds_pc_relative_labels(self):
        words = [0x0080006F, 0x00000013, 0x00000013]
        rendered = compile_c.render_tc_asm(
            words,
            {},
            source_names=["jump.bin"],
            stack_top=2032,
        )
        self.assertIn("jal x0, loc_00000008", rendered)
        self.assertIn("loc_00000008:", rendered)

    def test_rejects_pc_relative_target_outside_text(self):
        with self.assertRaisesRegex(compile_c.CompileError, "PC 相对目标"):
            compile_c.collect_labels([0x0080006F])

    def test_validate_words_reports_machine_code_address(self):
        with self.assertRaisesRegex(compile_c.CompileError, "0x00000000"):
            compile_c.validate_words([0x02000033], {})

    def test_build_command_forces_rv64i_code_only_settings(self):
        tools = compile_c.Toolchain("gcc", "objcopy", "objdump")
        command = compile_c.build_command(
            tools,
            sources=[Path("program.c")],
            startup=Path("start.S"),
            linker=Path("layout.ld"),
            elf=Path("program.elf"),
            map_file=Path("program.map"),
            stack_top=2032,
            optimization="2",
            extra_cflags=[],
        )
        for option in (
            "-march=rv64i",
            "-mabi=lp64",
            "-mno-relax",
            "-mno-save-restore",
            "-ffreestanding",
            "-nostdlib",
            "-fno-jump-tables",
            "-fno-tree-switch-conversion",
            "-Wl,--no-relax",
            "-lgcc",
        ):
            self.assertIn(option, command)
        self.assertFalse(any("rv64im" in item for item in command))

    def test_auto_toolchain_prefix_falls_back(self):
        available = {
            "riscv-none-elf-gcc": "/toolchain/riscv-none-elf-gcc",
            "riscv-none-elf-objcopy": "/toolchain/riscv-none-elf-objcopy",
            "riscv-none-elf-objdump": "/toolchain/riscv-none-elf-objdump",
        }
        with patch.object(compile_c.shutil, "which", side_effect=available.get):
            tools = compile_c.find_toolchain("auto")
        self.assertEqual(tools.gcc, available["riscv-none-elf-gcc"])

    def test_linker_rejects_all_data_sections(self):
        linker = (TOOLCHAIN_DIR / "tc-rv64-code-only.ld").read_text("utf-8")
        self.assertIn("ASSERT(SIZEOF(.rodata) == 0", linker)
        self.assertIn("ASSERT(SIZEOF(.data) == 0", linker)
        self.assertIn("ASSERT(SIZEOF(.bss) == 0", linker)

    def test_main_rejects_unaligned_stack_before_tool_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            with patch.object(compile_c, "find_toolchain") as find_toolchain:
                with redirect_stderr(StringIO()):
                    result = compile_c.main([str(source), "--stack-top", "2047"])
        self.assertEqual(result, 1)
        find_toolchain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
