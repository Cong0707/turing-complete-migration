# 从 C 生成 RV64I `.assembly`

## 目标

`examples/rv64i/c-toolchain/` 提供以下单向流程：

```text
freestanding C
  -> GCC RV64I/LP64 编译和静态链接
  -> 地址 0 开始的 ELF .text
  -> little-endian 原始机器码
  -> 指令白名单验证
  -> Turing Complete U32 .assembly
```

它只生成文件，不读取或修改 Turing Complete 存档。

## 文件

| 文件 | 用途 |
| --- | --- |
| `compile_c.py` | 调用交叉工具链、验证机器码并生成 `.assembly` |
| `build.sh` | Linux/macOS shell 入口 |
| `start.S` | 设置栈顶、调用 `main`、返回后原地循环 |
| `tc-rv64-code-only.ld` | 将 `.text` 链接到地址 0，并拒绝数据段 |
| `example.c` | 不依赖全局数据的最小 C 示例 |

Python 部分只使用标准库，不需要安装任何 `pip` 包。

## 依赖

需要 GNU RISC-V bare-metal 工具链中的：

```text
riscv64-unknown-elf-gcc
riscv64-unknown-elf-objcopy
riscv64-unknown-elf-objdump
```

Ubuntu/Debian 常见安装命令：

```bash
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf python3
```

脚本也会自动尝试 `riscv-none-elf-` 前缀。其他前缀可以用 `--prefix` 指定。

## 使用

```bash
cd examples/rv64i/c-toolchain
sh build.sh example.c -o example.assembly
```

等价的直接命令：

```bash
python3 compile_c.py example.c -o example.assembly
```

常用选项：

```bash
python3 compile_c.py program.c \
  -o program.assembly \
  --stack-top 2032 \
  --max-code-bytes 131072 \
  -O 2
```

若工具链命令不是默认名称：

```bash
python3 compile_c.py program.c \
  -o program.assembly \
  --prefix /opt/riscv/bin/riscv64-unknown-elf-
```

成功时生成：

```text
program.assembly
program-build/program.elf
program-build/program.text.bin
program-build/program.objdump.txt
program-build/program.map
```

## 实际 GCC 约束

脚本构造的核心参数为：

```text
-march=rv64i -mabi=lp64
-mcmodel=medany -mstrict-align
-mno-relax -mno-save-restore
-ffreestanding -nostdlib -nostartfiles -fno-builtin
-fno-pic -fno-pie -fno-stack-protector
-fno-jump-tables -fno-tree-switch-conversion
-Wl,--gc-sections -Wl,--no-relax -lgcc
```

`-march=rv64i` 禁止 GCC 使用 M/A/F/D/C/V 等扩展。即使工具链或链接库仍意外产生了
其他编码，Python 还会对最终 `.text` 中的每一条 32 位指令做第二次检查。

`libgcc` 用于满足编译器可能生成的基础辅助函数。最终结果仍必须通过同一指令白名单，
所以链接到包含乘除扩展指令的错误库时会失败，而不是生成不可运行的程序。

## 启动和内存布局

链接地址从 `0` 开始，与当前 RV64 指令 RAM 的程序起点一致。`start.S` 执行：

```asm
lui  sp, %hi(__stack_top)
addi sp, sp, %lo(__stack_top)
jal  ra, main
```

`main` 返回后进入无限跳转。返回值保留在 `a0`。

默认栈顶是 `2032`，即 `0x7f0`，满足 RV64 LP64 ABI 的 16 字节对齐。需要根据实际数据
RAM 地址空间调整时使用 `--stack-top`；脚本会拒绝零、负数和未对齐值。

## 为什么只输出代码

用户当前 RV64 是 Harvard 架构：指令 RAM 与 64 位数据 RAM 分离。已确认最新版可以把
汇编结果装入指令 RAM，但尚未确认一种可重复的方式同时初始化独立数据 RAM。因此当前
链接脚本要求以下段全部为空：

```text
.rodata
.data
.bss
```

这意味着当前支持：

- 局部自动变量和栈上数组；
- 纯整数控制流、函数调用、分支和移位；
- CPU 已实现的 RV64I load/store；
- 能由 RV64I 或合格 `libgcc` 实现的整数运算。

当前不支持：

- 全局或 `static` 变量；
- 字符串字面量、全局常量表和初始化数组；
- libc、文件、控制台、系统调用和动态分配；
- C++ 运行时、构造函数、异常和 RTTI；
- 依赖独立数据 RAM 预装镜像的程序。

默认关闭 jump table 和 switch table，使常见 `switch` 尽量编译成代码分支。如果 GCC
仍生成只读表，链接会带着明确错误退出。

扩展到数据镜像时，应增加独立的 `program.data.bin` 及明确的数据 RAM 导入步骤，不能
简单地把 `.data` 拼到指令字节后面。

## `.assembly` 输出格式

生成文件使用：

```asm
; 00000000: add x10,x11,x12
U32 0x00c58533
```

`U32` 是当前 Turing Complete 汇编器的原生数据语句。配合项目中 `spec.isa` 的：

```ini
endianness = little
```

上述值写为：

```text
33 85 c5 00
```

这些值已经完成 GCC 汇编、链接和重定位。使用者不需要也不应再次处理标签或倒转字节。

## 失败保护

生成器在以下情况下退出且不保留旧的目标 `.assembly`：

- 缺少源文件、启动文件、链接脚本或交叉工具链；
- `.text` 为空、不是 4 字节的倍数或超过容量限制；
- 出现当前 CPU 白名单以外的 opcode/funct 编码；
- 出现 `.rodata/.data/.bss`；
- 栈顶未满足 16 字节对齐；
- GCC、objcopy 或 objdump 返回失败。

ELF、map、objdump 和原始 `.text.bin` 会留在构建目录，便于定位实际生成了哪条不兼容
指令。

## 当前验证边界

仓库测试已经验证：

- 12 个允许 opcode 组和主要 funct 限制；
- `MUL`、`FENCE`、CSR 和未知 opcode 会被拒绝；
- raw binary 按 little-endian 解成 `U32`；
- `U32 0x00c58533` 经 2.1.277 同步的 `isa_spec` 解析器输出
  `33 85 c5 00`；
- GCC 命令包含 RV64I、LP64、freestanding、无 relax 和无表跳转约束；
- 链接脚本拒绝三类数据段。

按用户要求，本次没有在 Windows 本机安装或运行 RISC-V GCC。真实 GCC 编译、链接和游戏
执行需要在用户已有的 Ubuntu 工具链环境中进行人工验收。
