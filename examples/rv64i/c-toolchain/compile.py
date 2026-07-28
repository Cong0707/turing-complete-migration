#!/usr/bin/env python3
"""Convert a linked RV64I ELF into ASM accepted by Turing Complete."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import sys


DEFAULT_OBJDUMP = "riscv64-unknown-elf-objdump"


class CompileError(RuntimeError):
    """A user-facing conversion error."""


@dataclass(frozen=True)
class Instruction:
    address: int
    word: int
    text: str


OBJDUMP_LINE = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]+)\s+(.+?)\s*$"
)


def run_objdump(elf: Path, objdump: str = DEFAULT_OBJDUMP) -> str:
    executable = shutil.which(objdump)
    if executable is None:
        raise CompileError(f"找不到工具：{objdump}")

    commands = [
        [executable, "-d", "-M", "no-aliases,numeric", str(elf)],
        [executable, "-d", str(elf)],
    ]
    last_error = ""
    for command in commands:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            return completed.stdout
        last_error = (completed.stdout or "") + (completed.stderr or "")
    raise CompileError(f"objdump 失败：\n{last_error}")


def parse_objdump(text: str) -> list[Instruction]:
    instructions: list[Instruction] = []
    seen: set[int] = set()
    for line in text.splitlines():
        match = OBJDUMP_LINE.match(line)
        if match is None:
            continue
        encoded = match.group(2)
        if len(encoded) != 8:
            raise CompileError(
                f"objdump 出现非 32 位指令：{line.strip()}；请确认 -march=rv64i"
            )
        address = int(match.group(1), 16)
        if address in seen:
            raise CompileError(f"objdump 中出现重复地址：0x{address:x}")
        seen.add(address)
        instructions.append(
            Instruction(
                address=address,
                word=int(encoded, 16),
                text=match.group(3).strip(),
            )
        )
    if not instructions:
        raise CompileError("objdump 中没有找到 32 位指令")
    return instructions


def validate_layout(instructions: list[Instruction]) -> None:
    if instructions[0].address != 0:
        raise CompileError(
            f"第一条指令地址是 0x{instructions[0].address:x}，不是 -Ttext=0 预期的 0"
        )
    for index, instruction in enumerate(instructions):
        expected = index * 4
        if instruction.address != expected:
            raise CompileError(
                f"指令地址不连续：期望 0x{expected:x}，实际 0x{instruction.address:x}"
            )


def sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    return (value ^ sign_bit) - sign_bit


def validate_rv64i_word(word: int) -> str | None:
    opcode = word & 0x7F
    funct3 = (word >> 12) & 0x7
    funct7 = (word >> 25) & 0x7F

    if opcode == 0x33:
        allowed = {
            (0b000, 0x00),
            (0b000, 0x20),
            (0b001, 0x00),
            (0b010, 0x00),
            (0b011, 0x00),
            (0b100, 0x00),
            (0b101, 0x00),
            (0b101, 0x20),
            (0b110, 0x00),
            (0b111, 0x00),
        }
        return None if (funct3, funct7) in allowed else "不支持的 OP funct"

    if opcode == 0x13:
        if funct3 in {0b000, 0b010, 0b011, 0b100, 0b110, 0b111}:
            return None
        funct6 = (word >> 26) & 0x3F
        if funct3 == 0b001 and funct6 == 0x00:
            return None
        if funct3 == 0b101 and funct6 in {0x00, 0x10}:
            return None
        return "不支持的 OP-IMM shift funct"

    if opcode == 0x03:
        return None if funct3 in {0, 1, 2, 3, 4, 5, 6} else "不支持的 LOAD"

    if opcode == 0x23:
        return None if funct3 in {0, 1, 2, 3} else "不支持的 STORE"

    if opcode == 0x63:
        return None if funct3 in {0, 1, 4, 5, 6, 7} else "不支持的 BRANCH"

    if opcode in {0x37, 0x17, 0x6F}:
        return None

    if opcode == 0x67:
        return None if funct3 == 0 else "JALR funct3 必须为 0"

    if opcode == 0x73:
        return None if word in {0x00000073, 0x00100073} else "只支持 ECALL/EBREAK"

    if opcode == 0x1B:
        if funct3 == 0b000:
            return None
        if funct3 == 0b001 and funct7 == 0x00:
            return None
        if funct3 == 0b101 and funct7 in {0x00, 0x20}:
            return None
        return "不支持的 OP-IMM-32"

    if opcode == 0x3B:
        allowed = {
            (0b000, 0x00),
            (0b000, 0x20),
            (0b001, 0x00),
            (0b101, 0x00),
            (0b101, 0x20),
        }
        return None if (funct3, funct7) in allowed else "不支持的 OP-32"

    return f"不支持的 opcode 0x{opcode:02x}"


def control_flow_target(word: int, address: int) -> int | None:
    opcode = word & 0x7F
    if opcode == 0x63:
        immediate = (
            (((word >> 31) & 0x1) << 12)
            | (((word >> 25) & 0x3F) << 5)
            | (((word >> 8) & 0xF) << 1)
            | (((word >> 7) & 0x1) << 11)
        )
        return address + sign_extend(immediate, 13)
    if opcode == 0x6F:
        immediate = (
            (((word >> 31) & 0x1) << 20)
            | (((word >> 21) & 0x3FF) << 1)
            | (((word >> 20) & 0x1) << 11)
            | (((word >> 12) & 0xFF) << 12)
        )
        return address + sign_extend(immediate, 21)
    return None


def collect_labels(instructions: list[Instruction]) -> dict[int, str]:
    addresses = {instruction.address for instruction in instructions}
    labels = {instructions[0].address: "start"}
    for instruction in instructions:
        target = control_flow_target(instruction.word, instruction.address)
        if target is None:
            continue
        if target not in addresses:
            raise CompileError(
                f"0x{instruction.address:08x} 的跳转目标 0x{target:x} "
                "不是 objdump 中的指令地址"
            )
        labels.setdefault(target, f"loc_{target:08x}")
    return labels


def decode_instruction(instruction: Instruction, labels: dict[int, str]) -> str:
    word = instruction.word
    address = instruction.address
    reason = validate_rv64i_word(word)
    if reason is not None:
        raise CompileError(
            f"0x{address:08x}: 0x{word:08x} ({instruction.text}): {reason}"
        )

    opcode = word & 0x7F
    rd = (word >> 7) & 0x1F
    funct3 = (word >> 12) & 0x7
    rs1 = (word >> 15) & 0x1F
    rs2 = (word >> 20) & 0x1F
    funct7 = (word >> 25) & 0x7F

    if opcode == 0x33:
        mnemonic = {
            (0, 0x00): "add",
            (0, 0x20): "sub",
            (1, 0x00): "sll",
            (2, 0x00): "slt",
            (3, 0x00): "sltu",
            (4, 0x00): "xor",
            (5, 0x00): "srl",
            (5, 0x20): "sra",
            (6, 0x00): "or",
            (7, 0x00): "and",
        }[(funct3, funct7)]
        return f"{mnemonic} x{rd}, x{rs1}, x{rs2}"

    if opcode == 0x13:
        if funct3 == 1:
            return f"slli x{rd}, x{rs1}, {(word >> 20) & 0x3F}"
        if funct3 == 5:
            mnemonic = "srai" if ((word >> 26) & 0x3F) == 0x10 else "srli"
            return f"{mnemonic} x{rd}, x{rs1}, {(word >> 20) & 0x3F}"
        mnemonic = {0: "addi", 2: "slti", 3: "sltiu", 4: "xori", 6: "ori", 7: "andi"}[
            funct3
        ]
        immediate = sign_extend((word >> 20) & 0xFFF, 12)
        return f"{mnemonic} x{rd}, x{rs1}, {immediate}"

    if opcode == 0x03:
        mnemonic = {0: "lb", 1: "lh", 2: "lw", 3: "ld", 4: "lbu", 5: "lhu", 6: "lwu"}[
            funct3
        ]
        immediate = sign_extend((word >> 20) & 0xFFF, 12)
        return f"{mnemonic} x{rd}, {immediate}(x{rs1})"

    if opcode == 0x23:
        mnemonic = {0: "sb", 1: "sh", 2: "sw", 3: "sd"}[funct3]
        immediate = sign_extend(((word >> 25) << 5) | ((word >> 7) & 0x1F), 12)
        return f"{mnemonic} x{rs2}, {immediate}(x{rs1})"

    if opcode == 0x63:
        mnemonic = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}[
            funct3
        ]
        target = control_flow_target(word, address)
        assert target is not None
        return f"{mnemonic} x{rs1}, x{rs2}, {labels[target]}"

    if opcode == 0x37:
        return f"lui x{rd}, 0x{(word >> 12) & 0xFFFFF:x}"

    if opcode == 0x17:
        return f"auipc x{rd}, 0x{(word >> 12) & 0xFFFFF:x}"

    if opcode == 0x6F:
        target = control_flow_target(word, address)
        assert target is not None
        return f"jal x{rd}, {labels[target]}"

    if opcode == 0x67:
        immediate = sign_extend((word >> 20) & 0xFFF, 12)
        return f"jalr x{rd}, {immediate}(x{rs1})"

    if opcode == 0x73:
        return "ecall" if word == 0x00000073 else "ebreak"

    if opcode == 0x1B:
        if funct3 == 0:
            immediate = sign_extend((word >> 20) & 0xFFF, 12)
            return f"addiw x{rd}, x{rs1}, {immediate}"
        mnemonic = "slliw" if funct3 == 1 else (
            "sraiw" if funct7 == 0x20 else "srliw"
        )
        return f"{mnemonic} x{rd}, x{rs1}, {(word >> 20) & 0x1F}"

    if opcode == 0x3B:
        mnemonic = {
            (0, 0x00): "addw",
            (0, 0x20): "subw",
            (1, 0x00): "sllw",
            (5, 0x00): "srlw",
            (5, 0x20): "sraw",
        }[(funct3, funct7)]
        return f"{mnemonic} x{rd}, x{rs1}, x{rs2}"

    raise CompileError(f"没有解码 0x{word:08x} 的处理器")


def render_asm(instructions: list[Instruction], source_name: str) -> str:
    validate_layout(instructions)
    labels = collect_labels(instructions)
    lines = [
        "# Generated from linked RV64I ELF for Turing Complete",
        f"# Source ELF: {source_name}",
        "",
    ]
    for instruction in instructions:
        if instruction.address in labels:
            lines.append(f"{labels[instruction.address]}:")
        #lines.append(f"# {instruction.address:08x}: {instruction.text}")
        lines.append(f"    {decode_instruction(instruction, labels)}")
    lines.append("")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="把原流程生成的 RV64I ELF 转成最新版可直接输入的 ASM"
    )
    result.add_argument("elf", type=Path, help="已经链接的 RV64I ELF")
    result.add_argument("-o", "--output", type=Path, help="输出 .asm；不指定则写到 stdout")
    result.add_argument(
        "--objdump",
        default=DEFAULT_OBJDUMP,
        help=f"objdump 命令，默认 {DEFAULT_OBJDUMP}",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        elf = args.elf.expanduser().resolve()
        if not elf.is_file():
            raise CompileError(f"ELF 不存在：{elf}")
        dump = run_objdump(elf, args.objdump)
        instructions = parse_objdump(dump)
        output = render_asm(instructions, elf.name)
        if args.output is None:
            sys.stdout.write(output)
        else:
            target = args.output.expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output, encoding="utf-8", newline="\n")
            print(f"完成：{target}", file=sys.stderr)
            print(f"指令：{len(instructions)}", file=sys.stderr)
        return 0
    except CompileError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
