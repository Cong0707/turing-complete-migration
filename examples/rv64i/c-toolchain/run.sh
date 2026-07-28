#!/bin/sh

if [ $# -ne 1 ]; then
    echo "Usage: ./run.sh test.cpp"
    exit 1
fi

SRC="$1"
ELF=temp.elf

# 生成可执行文件（链接后）
riscv64-unknown-elf-gcc \
    -march=rv64i -mabi=lp64 \
    -ffreestanding -nostdlib -lgcc -O0 \
    -fno-stack-protector \
    -fomit-frame-pointer \
    -Wl,-Ttext=0 \
    -fno-keep-static-consts \
    -fno-tree-sra \
    -fno-tree-slp-vectorize \
    -fno-tree-ccp \
    -fno-pic -fno-pie \
    _start.S \
    "$SRC" -o "$ELF"

echo "=======objdump========"
riscv64-unknown-elf-objdump -d "$ELF"

echo
echo "=======code========"
python3 compile.py "$ELF"

rm -rf "$ELF"
