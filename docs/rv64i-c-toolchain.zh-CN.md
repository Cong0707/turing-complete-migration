# 与原流程兼容的 C/C++ → RV64I ASM

## 目标

本工具不重新设计用户的编译环境，而是严格沿用用户已有流程：

```text
test.cpp
  -> riscv64-unknown-elf-gcc（用户原参数）
  -> temp.elf
  -> riscv64-unknown-elf-objdump -d
  -> compile.py
  -> 最新版 Turing Complete 可直接输入的 test.asm
```

旧版最后由 `encode.py` 输出四个小端二进制字节；新版最后由 `compile.py` 输出真实 RV64I
助记符和标签。编译、链接和启动代码保持不变。

工具只生成文件，不读取或修改游戏存档。

## 文件

```text
examples/rv64i/c-toolchain/
  run.sh
  build.sh
  compile.py
  _start.S
  README.md
```

其中：

- `run.sh`：用户原流程的最新版 ASM 输出版本；
- `build.sh`：兼容入口，直接调用 `run.sh`；
- `compile.py`：读取已链接 ELF 的 objdump，生成可直接输入的 ASM；
- `_start.S`：按用户原文件保留；
- `README.md`：最短使用说明。

Python 只使用标准库，没有 `pip` 依赖。

## 与用户原 `run.sh` 的对应关系

保留的 GCC 命令为：

```bash
riscv64-unknown-elf-gcc \
    -march=rv64i -mabi=lp64 \
    -ffreestanding -nostdlib -lgcc -O0 \
    -fno-stack-protector \
    -fomit-frame-pointer \
    -Wl,-Ttext=0 \
    -fno-pic -fno-pie \
    _start.S \
    "$SRC" -o temp.elf
```

没有加入：

- 自定义链接脚本；
- `-O2`；
- C-only 限制；
- 数据段拒绝规则；
- 额外 ABI、relax 或 jump-table 参数；
- 新工具链前缀。

输入仍由文件后缀交给 GCC 判断，所以用户原来的 `.cpp` 文件可以直接使用。

## 启动代码

`_start.S` 按用户提供内容保留：

```asm
    .section .text
    .globl _start
_start:
    addi sp, x0, 2047
    addi x1, x0, 128
    jal ra, main

end:
    j end
```

本工具不调整栈对齐，也不删除或改写 `x1 = 128`。GNU 汇编器负责把 `j end` 等伪指令
编码成 RV64I 机器码，`compile.py` 再将最终机器码输出为 `spec.isa` 支持的形式。

## 安装到用户原目录

将以下四个文件复制到：

```text
~/congProjects/riscv/
```

文件：

```text
run.sh
build.sh
compile.py
_start.S
```

原来的这些文件无需修改：

```text
a.cpp
b.cpp
btc.cpp
sha256.cpp
encode.py
```

设置 shell 文件权限：

```bash
chmod +x run.sh build.sh
```

## 使用

与原流程相同，只接收一个源文件：

```bash
./run.sh a.cpp
```

也可以使用兼容入口：

```bash
./build.sh a.cpp
```

执行过程仍打印：

```text
=======objdump========
...

=======asm========
...
```

生成：

```text
a.asm
```

临时 `temp.elf` 在成功或失败退出时删除。

## 直接使用 `compile.py`

如果已经有原流程链接出的 ELF：

```bash
python3 compile.py temp.elf -o program.asm
```

不指定 `-o` 时，ASM 写到标准输出，行为接近旧 `encode.py`：

```bash
python3 compile.py temp.elf > program.asm
```

可以显式指定 objdump 命令：

```bash
python3 compile.py temp.elf \
  --objdump riscv64-unknown-elf-objdump \
  -o program.asm
```

## ASM 输出

输出只包含项目 `spec.isa` 已定义的 RV64I 助记符：

```asm
# Generated from linked RV64I ELF for Turing Complete
# Source ELF: temp.elf

start:
# 00000000: addi sp,zero,2047
    addi x2, x0, 2047
# 00000004: addi ra,zero,128
    addi x1, x0, 128
# 00000008: jal ra,main
    jal x1, loc_00000010

loc_00000010:
    addi x10, x0, 0
```

以下内容不会进入最终文件：

- 旧版 `0bxxxxxxxx` 四字节行；
- `U32` 或 `.word`；
- GNU `.section/.globl/.type` 指令；
- objdump 的地址作为汇编立即数；
- `spec.isa` 未实现的指令。

## 为什么从最终机器码反解

直接使用 `gcc -S` 会得到 GNU 汇编源码，其中可能包含：

- `.section`、`.align`、`.type`、`.size`；
- 局部数字标签；
- 重定位表达式；
- GNU 伪指令；
- 游戏 `spec.isa` 不认识的语法。

本流程先按用户原命令完成链接，再从 objdump 的每个 32 位机器码反解。因此函数位置、
branch 和 jal 偏移已经确定。`compile.py` 为 PC-relative 目标生成 `loc_XXXXXXXX` 标签，
输出可读且能由当前 `spec.isa` 重新汇编。

## 检查和失败条件

`compile.py` 会拒绝：

- ELF 不存在；
- 找不到 `riscv64-unknown-elf-objdump`；
- objdump 执行失败；
- 出现 16 位压缩指令或其他非 32 位编码；
- 第一条指令不是地址 0；
- 指令地址不是连续的 4 字节序列；
- 出现 CPU/`spec.isa` 没有实现的 opcode 或 funct；
- branch/jal 目标不是 objdump 中的指令地址。

这些检查不会改变原 ELF，只避免生成地址已经错位或 CPU 无法执行的 ASM。

## 数据段行为

本流程不再擅自拒绝 `.data/.rodata/.bss`，因为用户原 GCC/encode 流程没有这个限制。

但必须明确：旧 `encode.py` 只遍历 `objdump -d` 的指令，本流程也只转换可执行指令，不会
额外生成数据 RAM 镜像。对于 `a.cpp` 中的全局数组，最终运行结果仍取决于用户原来如何
向数据 RAM 写入初始化数据。这是原流程既有边界，本次不改变。

## 验证

不安装 RISC-V 工具链的纯 Python 测试覆盖：

- 用户原 objdump 行格式；
- 用户原 GCC 参数文本；
- `_start.S` 的 `2047`、`128`、`jal main` 和死循环；
- 12 个允许 opcode 组；
- MUL/FENCE/CSR 等拒绝；
- 32 位指令和连续地址要求；
- branch/jal 标签重建；
- 直接 ASM 输出而不是二进制文本。

另使用 2.1.277 同步的 `isa_spec` 解析器，将 65 条、260 字节 RV64I 冒烟程序执行：

```text
原 ASM -> 机器码 -> compile.py 解码 ASM -> 重新汇编
```

前后 260 字节完全一致。

按用户要求，本次没有在 Windows 本机安装或调用 RISC-V GCC。实际 `.cpp` 编译由用户在
原 Ubuntu 目录中执行 `./run.sh a.cpp` 验收。
