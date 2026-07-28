#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: ./run.sh test.cpp" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC="$1"
ELF=temp.elf
OUT="${SRC%.*}.asm"

cleanup() {
    rm -f "$ELF"
}
trap cleanup EXIT INT TERM

# 保留用户原有 GCC 命令和参数。
riscv64-unknown-elf-gcc \
    -march=rv64i -mabi=lp64 \
    -ffreestanding -nostdlib -lgcc -O0 \
    -fno-stack-protector \
    -fomit-frame-pointer \
    -Wl,-Ttext=0 \
    -fno-pic -fno-pie \
    "$SCRIPT_DIR/_start.S" \
    "$SRC" -o "$ELF"

echo "=======objdump========"
riscv64-unknown-elf-objdump -d "$ELF"

echo
echo "=======asm========"
python3 "$SCRIPT_DIR/compile.py" "$ELF" -o "$OUT"
cat "$OUT"

echo
echo "Wrote $OUT"
