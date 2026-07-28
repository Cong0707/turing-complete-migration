# C → Turing Complete RV64I 编译流程

这套文件只生成程序，不修改 Turing Complete 存档，也不会自动安装交叉编译器。

## 依赖

Ubuntu/Debian 上需要能执行：

```text
riscv64-unknown-elf-gcc
riscv64-unknown-elf-objcopy
riscv64-unknown-elf-objdump
python3
```

Ubuntu 中常见的软件包安装方式是：

```bash
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf python3
```

Python 脚本只使用标准库，没有额外的 `pip` 依赖。

## 一条命令

```bash
./build.sh example.c -o example.assembly
```

如果脚本没有可执行权限：

```bash
sh build.sh example.c -o example.assembly
```

也可以直接调用 Python：

```bash
python3 compile_c.py example.c -o example.assembly
```

输出：

```text
example.assembly
example-build/example.elf
example-build/example.text.bin
example-build/example.objdump.txt
example-build/example.map
```

`example.assembly` 使用最新版汇编器支持的形式：

```text
; 00000000: lui x2,0x0
U32 0x00000137
```

配合 `endianness = little` 的 RV64I `spec.isa`，每个 `U32` 会写成标准 RISC-V
little-endian 四字节。

## 可调参数

```bash
python3 compile_c.py program.c \
  -o program.assembly \
  --stack-top 2032 \
  --max-code-bytes 131072 \
  -O 2
```

脚本默认依次查找 `riscv64-unknown-elf-` 和 `riscv-none-elf-`。也可以明确指定
其他工具链前缀：

```bash
python3 compile_c.py program.c -o program.assembly --prefix riscv-none-elf-
```

## 第一版限制

这是一条针对当前 RV64 Harvard 架构的“代码区直出”流程：

- 支持 freestanding C 和 `libgcc` 中仍能用 RV64I 实现的辅助函数。
- 不支持 libc、操作系统调用或标准启动文件。
- 不支持全局/静态数据、字符串、只读表和 BSS。
- 链接器发现 `.rodata`、`.data` 或 `.bss` 非空会直接失败。
- 默认关闭 jump table 和 switch table，尽量让 `switch` 保持为代码分支。
- Python 会逐条验证机器码，只允许 `spec.isa` 中的 12 个 opcode 组和对应 funct。
- `MISC-MEM/FENCE`、CSR、M/A/F/D/C/V 扩展会被拒绝。
- 初始栈顶必须 16 字节对齐。

局部自动变量和局部 `volatile` 变量可以放在栈上。需要全局数据时，必须先确定最新版
中独立数据 RAM 的装载方式，再扩展为代码镜像和数据镜像双输出。

## 导入游戏

把 `example.assembly` 的文本复制到使用同目录 `spec.isa` 的 RV64 架构程序编辑器中。
生成文件中的每条 `U32` 都是一条已经完成链接和重定位的机器指令；不要再对其做字节倒序。

## 返回值和结束行为

`start.S` 调用 `main`。`main` 返回以后，CPU 会停在一个无限跳转中；返回值仍保留在
ABI 返回寄存器 `a0`。没有操作系统，因此 `return` 不会退出进程，也没有标准输出。
