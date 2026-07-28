# 与原流程兼容的 C/C++ → RV64I ASM

本目录以用户已有文件为基线，只替换最后的输出格式：

```text
test.cpp
  -> 原 riscv64-unknown-elf-gcc 命令
  -> temp.elf
  -> riscv64-unknown-elf-objdump -d
  -> compile.py
  -> 最新版可直接输入的 test.asm
```

## 直接替换

把以下文件复制到原来的 `~/congProjects/riscv/`：

```text
run.sh
build.sh
compile.py
_start.S
```

原来的 `a.cpp`、`b.cpp`、`btc.cpp`、`sha256.cpp` 和 `encode.py` 不需要改。

## 使用

```bash
chmod +x run.sh build.sh
./run.sh a.cpp
```

或：

```bash
./build.sh a.cpp
```

输出：

```text
a.asm
```

其中是可直接输入游戏的真实 RV64I 汇编：

```asm
start:
    addi x2, x0, 2047
    addi x1, x0, 128
    jal x1, loc_00000010
```

## 保留的原行为

- 输入仍是一个 `.cpp` 文件；
- 工具链仍是 `riscv64-unknown-elf-gcc`；
- 保留 `-march=rv64i -mabi=lp64`；
- 保留 `-ffreestanding -nostdlib -lgcc -O0`；
- 保留 `-fomit-frame-pointer` 和 `-Wl,-Ttext=0`；
- 保留 `_start.S` 的 `sp = 2047`；
- 保留 `_start.S` 的 `x1 = 128`；
- 编译后仍打印完整 objdump；
- 临时文件仍使用 `temp.elf`，结束时删除。

## 唯一实质变化

旧 `encode.py` 把每条指令打印成四个小端二进制字节。最新版直接输入 ASM，所以
`compile.py` 读取同一个 ELF 的 objdump 机器码，将其反解为 `spec.isa` 已定义的助记符，
并为 branch/jal 重建标签。

`compile.py` 不重新编译、不改变 GCC 参数，也不改变 `_start.S`。

## 数据说明

此流程与旧 `encode.py` 一样只处理 `objdump -d` 中的可执行指令，不额外导出 `.data`、
`.rodata` 或 `.bss`。如果原程序依赖初始化全局数组，是否能正确工作仍取决于你原有的
数据 RAM 写入方式；本次不擅自改变该行为。

Python 只使用标准库，没有 `pip` 依赖。
