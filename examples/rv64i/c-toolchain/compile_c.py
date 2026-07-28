#!/usr/bin/env python3
"""Compile freestanding C to a Turing Complete RV64I .assembly file."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys


DEFAULT_PREFIXES = ("riscv64-unknown-elf-", "riscv-none-elf-")
DEFAULT_STACK_TOP = 2032
DEFAULT_MAX_CODE_BYTES = 131072


class CompileError(RuntimeError):
    """A user-facing build or validation error."""


@dataclass(frozen=True)
class Toolchain:
    gcc: str
    objcopy: str
    objdump: str


@dataclass(frozen=True)
class Instruction:
    address: int
    word: int
    text: str


def parse_int(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"不是有效整数：{value}") from exc


def find_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise CompileError(f"找不到工具：{name}")
    return resolved


def find_toolchain(prefix: str) -> Toolchain:
    prefixes = DEFAULT_PREFIXES if prefix == "auto" else (prefix,)
    failures: list[str] = []
    for candidate in prefixes:
        try:
            return Toolchain(
                gcc=find_tool(candidate + "gcc"),
                objcopy=find_tool(candidate + "objcopy"),
                objdump=find_tool(candidate + "objdump"),
            )
        except CompileError as exc:
            failures.append(str(exc))
    tried = ", ".join(prefixes)
    raise CompileError(
        f"找不到完整的 RISC-V 交叉工具链（尝试过：{tried}）：\n"
        + "\n".join(failures)
    )


def run(command: list[str], *, cwd: Path, capture: bool = False) -> str:
    print("+", shlex.join(command))
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if completed.returncode != 0:
        details = ""
        if capture:
            details = "\n" + (completed.stdout or "") + (completed.stderr or "")
        raise CompileError(
            f"命令失败，退出码 {completed.returncode}: {shlex.join(command)}{details}"
        )
    return completed.stdout if capture else ""


def validate_rv64i_word(word: int) -> str | None:
    """Return None for the supported RV64I subset, otherwise an error reason."""

    opcode = word & 0x7F
    funct3 = (word >> 12) & 0x7
    funct7 = (word >> 25) & 0x7F

    if opcode == 0x33:  # OP
        allowed = {
            (0b000, 0x00),  # ADD
            (0b000, 0x20),  # SUB
            (0b001, 0x00),  # SLL
            (0b010, 0x00),  # SLT
            (0b011, 0x00),  # SLTU
            (0b100, 0x00),  # XOR
            (0b101, 0x00),  # SRL
            (0b101, 0x20),  # SRA
            (0b110, 0x00),  # OR
            (0b111, 0x00),  # AND
        }
        return None if (funct3, funct7) in allowed else "不支持的 OP funct3/funct7"

    if opcode == 0x13:  # OP-IMM
        if funct3 in {0b000, 0b010, 0b011, 0b100, 0b110, 0b111}:
            return None
        funct6 = (word >> 26) & 0x3F
        if funct3 == 0b001 and funct6 == 0x00:
            return None
        if funct3 == 0b101 and funct6 in {0x00, 0x10}:
            return None
        return "不支持的 OP-IMM funct3/funct6"

    if opcode == 0x03:  # LOAD
        return None if funct3 in {0, 1, 2, 3, 4, 5, 6} else "不支持的 LOAD funct3"

    if opcode == 0x23:  # STORE
        return None if funct3 in {0, 1, 2, 3} else "不支持的 STORE funct3"

    if opcode == 0x63:  # BRANCH
        return None if funct3 in {0, 1, 4, 5, 6, 7} else "不支持的 BRANCH funct3"

    if opcode in {0x37, 0x17, 0x6F}:  # LUI, AUIPC, JAL
        return None

    if opcode == 0x67:  # JALR
        return None if funct3 == 0 else "JALR funct3 必须为 0"

    if opcode == 0x73:  # SYSTEM
        return None if word in {0x00000073, 0x00100073} else "只支持 ECALL/EBREAK"

    if opcode == 0x1B:  # OP-IMM-32
        if funct3 == 0b000:
            return None
        if funct3 == 0b001 and funct7 == 0x00:
            return None
        if funct3 == 0b101 and funct7 in {0x00, 0x20}:
            return None
        return "不支持的 OP-IMM-32 funct3/funct7"

    if opcode == 0x3B:  # OP-32
        allowed = {
            (0b000, 0x00),  # ADDW
            (0b000, 0x20),  # SUBW
            (0b001, 0x00),  # SLLW
            (0b101, 0x00),  # SRLW
            (0b101, 0x20),  # SRAW
        }
        return None if (funct3, funct7) in allowed else "不支持的 OP-32 funct3/funct7"

    return f"不支持的 opcode 0x{opcode:02x}"


OBJDUMP_LINE = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+(.+?)\s*$"
)


def parse_objdump(text: str) -> dict[int, Instruction]:
    instructions: dict[int, Instruction] = {}
    for line in text.splitlines():
        match = OBJDUMP_LINE.match(line)
        if match is None:
            continue
        address = int(match.group(1), 16)
        instructions[address] = Instruction(
            address=address,
            word=int(match.group(2), 16),
            text=match.group(3),
        )
    return instructions


def words_from_binary(data: bytes) -> list[int]:
    if len(data) == 0:
        raise CompileError("链接结果的 .text 为空")
    if len(data) % 4 != 0:
        raise CompileError(f".text 长度 {len(data)} 不是 4 的倍数，可能生成了压缩指令")
    return [item[0] for item in struct.iter_unpack("<I", data)]


def validate_words(words: list[int], disassembly: dict[int, Instruction]) -> None:
    errors: list[str] = []
    for index, word in enumerate(words):
        address = index * 4
        decoded = disassembly.get(address)
        if decoded is not None and decoded.word != word:
            errors.append(
                f"0x{address:08x}: objdump=0x{decoded.word:08x}, binary=0x{word:08x}"
            )
            continue
        reason = validate_rv64i_word(word)
        if reason is not None:
            asm = "" if decoded is None else f" ({decoded.text})"
            errors.append(f"0x{address:08x}: 0x{word:08x}{asm}: {reason}")
    if errors:
        preview = "\n".join(errors[:20])
        extra = "" if len(errors) <= 20 else f"\n……另有 {len(errors) - 20} 项"
        raise CompileError(f"生成了 CPU 未实现的指令：\n{preview}{extra}")


def render_tc_assembly(
    words: list[int],
    disassembly: dict[int, Instruction],
    *,
    source_names: list[str],
    stack_top: int,
) -> str:
    lines = [
        "; Generated by compile_c.py for Turing Complete RV64I",
        "; Sources: " + ", ".join(source_names),
        f"; Stack top: 0x{stack_top:x}",
        "; Each U32 value is emitted as four little-endian bytes by spec.isa.",
        "",
    ]
    for index, word in enumerate(words):
        address = index * 4
        decoded = disassembly.get(address)
        if decoded is not None:
            lines.append(f"; {address:08x}: {decoded.text}")
        else:
            lines.append(f"; {address:08x}: <no objdump text>")
        lines.append(f"U32 0x{word:08x}")
    lines.append("")
    return "\n".join(lines)


def build_command(
    tools: Toolchain,
    *,
    sources: list[Path],
    startup: Path,
    linker: Path,
    elf: Path,
    map_file: Path,
    stack_top: int,
    optimization: str,
    extra_cflags: list[str],
) -> list[str]:
    return [
        tools.gcc,
        "-march=rv64i",
        "-mabi=lp64",
        "-mcmodel=medany",
        "-mstrict-align",
        "-mno-relax",
        "-mno-save-restore",
        f"-O{optimization}",
        "-std=c11",
        "-ffreestanding",
        "-nostdlib",
        "-nostartfiles",
        "-fno-builtin",
        "-fno-pic",
        "-fno-pie",
        "-fno-stack-protector",
        "-fno-unwind-tables",
        "-fno-asynchronous-unwind-tables",
        "-fno-common",
        "-fno-jump-tables",
        "-fno-tree-switch-conversion",
        "-ffunction-sections",
        "-fdata-sections",
        "-msmall-data-limit=0",
        "-Wall",
        "-Wextra",
        *extra_cflags,
        str(startup),
        *(str(source) for source in sources),
        f"-Wl,-T,{linker}",
        "-Wl,--gc-sections",
        "-Wl,--no-relax",
        "-Wl,--build-id=none",
        "-Wl,--fatal-warnings",
        f"-Wl,--defsym=__stack_top={stack_top}",
        f"-Wl,-Map={map_file}",
        "-lgcc",
        "-o",
        str(elf),
    ]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="把 freestanding C 编译成 Turing Complete RV64I .assembly"
    )
    result.add_argument("sources", nargs="+", type=Path, help="一个或多个 .c 文件")
    result.add_argument("-o", "--output", type=Path, help="输出 .assembly 文件")
    result.add_argument(
        "--build-dir", type=Path, help="ELF/bin/map/objdump 中间产物目录"
    )
    result.add_argument(
        "--prefix",
        default="auto",
        help=(
            "交叉工具链前缀；默认 auto，依次尝试 "
            + "、".join(DEFAULT_PREFIXES)
        ),
    )
    result.add_argument(
        "--stack-top",
        type=parse_int,
        default=DEFAULT_STACK_TOP,
        help=f"初始栈顶地址，默认 {DEFAULT_STACK_TOP}",
    )
    result.add_argument(
        "--max-code-bytes",
        type=parse_int,
        default=DEFAULT_MAX_CODE_BYTES,
        help=f"最大代码字节数，默认 {DEFAULT_MAX_CODE_BYTES}",
    )
    result.add_argument(
        "-O",
        "--optimization",
        choices=["0", "1", "2", "3", "s"],
        default="2",
        help="GCC 优化等级，默认 2",
    )
    result.add_argument(
        "--cflag",
        action="append",
        default=[],
        help="额外传给 GCC 的单个参数，可重复",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    script_dir = Path(__file__).resolve().parent

    try:
        sources = [path.expanduser().resolve() for path in args.sources]
        for source in sources:
            if not source.is_file():
                raise CompileError(f"源文件不存在：{source}")
            if source.suffix.lower() != ".c":
                raise CompileError(f"第一版只支持 C 源文件：{source}")

        if args.stack_top <= 0 or args.stack_top % 16 != 0:
            raise CompileError("--stack-top 必须是正数且满足 16 字节对齐")
        if args.max_code_bytes <= 0:
            raise CompileError("--max-code-bytes 必须为正数")

        output = (
            args.output.expanduser().resolve()
            if args.output
            else sources[0].with_suffix(".assembly")
        )
        build_dir = (
            args.build_dir.expanduser().resolve()
            if args.build_dir
            else output.parent / (output.stem + "-build")
        )
        build_dir.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)

        tools = find_toolchain(args.prefix)
        startup = script_dir / "start.S"
        linker = script_dir / "tc-rv64-code-only.ld"
        if not startup.is_file() or not linker.is_file():
            raise CompileError("compile_c.py 必须与 start.S 和链接脚本放在同一目录")
        stem = output.stem
        elf = build_dir / f"{stem}.elf"
        binary = build_dir / f"{stem}.text.bin"
        dump = build_dir / f"{stem}.objdump.txt"
        map_file = build_dir / f"{stem}.map"

        print(f"工具链：{tools.gcc}")
        command = build_command(
            tools,
            sources=sources,
            startup=startup,
            linker=linker,
            elf=elf,
            map_file=map_file,
            stack_top=args.stack_top,
            optimization=args.optimization,
            extra_cflags=args.cflag,
        )
        run(command, cwd=build_dir)
        run(
            [tools.objcopy, "-O", "binary", "-j", ".text", str(elf), str(binary)],
            cwd=build_dir,
        )

        try:
            dump_text = run(
                [tools.objdump, "-d", "-M", "no-aliases,numeric", str(elf)],
                cwd=build_dir,
                capture=True,
            )
        except CompileError:
            dump_text = run(
                [tools.objdump, "-d", str(elf)], cwd=build_dir, capture=True
            )
        dump.write_text(dump_text, encoding="utf-8", newline="\n")

        data = binary.read_bytes()
        if len(data) > args.max_code_bytes:
            raise CompileError(
                f"代码大小 {len(data)} 超过限制 {args.max_code_bytes} 字节"
            )
        words = words_from_binary(data)
        disassembly = parse_objdump(dump_text)
        validate_words(words, disassembly)
        assembly = render_tc_assembly(
            words,
            disassembly,
            source_names=[source.name for source in sources],
            stack_top=args.stack_top,
        )
        output.write_text(assembly, encoding="utf-8", newline="\n")

        digest = sha256(data).hexdigest()
        print(f"完成：{output}")
        print(f"代码：{len(words)} 条指令，{len(data)} 字节")
        print(f"SHA-256：{digest}")
        print(f"中间产物：{build_dir}")
        return 0
    except CompileError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
