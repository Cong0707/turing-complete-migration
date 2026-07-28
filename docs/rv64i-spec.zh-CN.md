# RV64I `spec.isa` 说明

## 目标

`examples/rv64i/spec.isa` 为用户迁移后的 RV64 CPU 提供 Turing Complete 汇编器定义。
它按用户电路中实际存在的 12 个 opcode 分类生成，不尝试声明未实现的扩展。

目标游戏版本是 Turing Complete 2.1.278。语法基线来自
[`Stuffe/isa_spec`](https://github.com/Stuffe/isa_spec) 的提交 `24f317b`，该提交标记为
“Update from Turing Complete v2.1.277”。上游在 2.1.280 同步提交中没有修改 RV64I
规格，因此本文件使用的语法位于 2.1.278 可用范围内。

## 12 个 opcode 组

| 图中分类 | RISC-V 分类 | opcode | 指令 |
| --- | --- | --- | --- |
| 寄存器运算 | OP | `0110011` / `0x33` | `add sub sll slt sltu xor srl sra or and` |
| 立即数运算 | OP-IMM | `0010011` / `0x13` | `addi slti sltiu xori ori andi slli srli srai` |
| 立即数访存 | LOAD | `0000011` / `0x03` | `lb lh lw ld lbu lhu lwu` |
| 访存 | STORE | `0100011` / `0x23` | `sb sh sw sd` |
| 条件分支 | BRANCH | `1100011` / `0x63` | `beq bne blt bge bltu bgeu` |
| 上位立即数写入寄存器 | LUI | `0110111` / `0x37` | `lui` |
| 上位立即数写入 PC | AUIPC | `0010111` / `0x17` | `auipc` |
| 无条件跳转 | JAL | `1101111` / `0x6f` | `jal` |
| 无条件寄存器跳转 | JALR | `1100111` / `0x67` | `jalr` |
| 系统调用 | SYSTEM | `1110011` / `0x73` | `ecall ebreak` |
| 32 位立即数运算 | OP-IMM-32 | `0011011` / `0x1b` | `addiw slliw srliw sraiw` |
| 32 位寄存器运算 | OP-32 | `0111011` / `0x3b` | `addw subw sllw srlw sraw` |

这里的“32 位运算”是 RV64I 的 word 操作：结果按 32 位计算，再符号扩展到 64 位。
实际符号扩展必须由 CPU 硬件正确实现，`spec.isa` 只负责编码。

## 寄存器名称

同时支持 `x0..x31` 和标准 ABI 别名：

```text
zero ra sp gp tp
t0 t1 t2
s0/fp s1
a0 a1 a2 a3 a4 a5 a6 a7
s2 s3 s4 s5 s6 s7 s8 s9 s10 s11
t3 t4 t5 t6
```

## 单指令伪指令

文件还提供只展开为一条 32 位机器指令的常用伪指令：

- 分支：`beqz bnez bltz bgez bgtz blez bgt bgtu ble bleu`
- 跳转：`j`、`jal label`、`jr`、`ret`
- 数据：`li`（仅有符号 12 位）、`mv`、`not`、`neg`、`negw`
- 比较：`seqz`、`snez`、`sltz`、`sgtz`
- 扩展：`sext.w`、`zext.b`
- 空操作：`nop`

## 明确排除的内容

### 没有对应硬件分类

- `FENCE`、`FENCE.TSO`、`PAUSE` 和整个 `MISC-MEM` opcode `0x0f`
- Zicsr CSR 指令
- M、A、F、D、C、V 等扩展
- 特权指令、页表、异常返回等

### 多指令伪指令

没有加入：

```text
call tail jump lla
完整 32/64 位 li
使用 label 自动展开 AUIPC+LOAD 的访存形式
sext.b sext.h zext.h zext.w
```

原因不是这些序列无法手工编写，而是 `spec.isa` 的 `endianness` 会作用于一个定义的
完整输出。如果一个定义一次输出 64 位，在 little-endian 模式下可能同时倒转两条
32 位指令的字节和先后顺序。为保证当前 8 位指令存储器中的结果确定，本规格规定：
**每个定义只输出一条 32 位机器指令。**

例如大常量应显式写成：

```asm
lui a0, 0x12345
addi a0, a0, 0x678
```

远距离调用也应根据范围显式选择 `jal`，或自行编写 `auipc` + `jalr`。

## 端序依据

用户当前 RV64 架构的指令存储组件：

- 组件字宽：8 位
- 已有程序字节：标准 RISC-V little-endian
- 示例 `addi sp, sp, -16`：机器码字 `0xff010113`，现有程序字节为
  `13 01 01 ff`

因此使用：

```ini
[settings]
endianness = little
```

因为存储器字宽只有 8 位，存储组件自己的 word 端序不会在单字节内部再次调整顺序。

规格还设置：

```ini
line_comments = [";", "//", "#"]
```

因此常见的 `#` 汇编注释也能被忽略。

## C/GCC 编译流程

用户提供的 `riscv64-unknown-elf-gcc -march=rv64i -mabi=lp64`、`objdump` 和
`encode.py` 是旧版通过二进制写入程序的流程。项目现已提供：

```text
examples/rv64i/c-toolchain/
```

新流程仍由 GCC 完成汇编、链接和重定位，然后将最终 `.text` 反解为当前汇编器支持的
真实 RV64I 助记符，并为 PC-relative branch/jal 重建本地标签。Python 会逐条验证机器码
只使用本规格覆盖的编码。完整说明见 `docs/rv64i-c-toolchain.zh-CN.md`。

当前流程故意拒绝 `.rodata/.data/.bss`。用户 RV64 的指令 RAM 与数据 RAM 分离，在没有
明确的数据 RAM 装载协议前，把数据段附加到代码末尾会得到错误程序。

## 使用

目标目录中 `spec.isa` 必须与 RV64 的 `circuit.data` 同级：

```text
%APPDATA%\Turing Complete\schematics\architecture\RV64\
  circuit.data
  spec.isa
```

项目不会自动写入该路径。需要使用时，只复制：

```text
examples\rv64i\spec.isa
```

不要复制 `smoke-test.asm` 到架构根目录；它只是验证用汇编程序。

## 验证结果

使用 `Stuffe/isa_spec` 提交 `24f317b` 的源码和 Nim 2.2.10 构建验证器：

1. `spec.isa` 解析成功。
2. `smoke-test.asm` 汇编成功，共 65 条指令、260 字节。
3. 输出只出现以下 12 个 opcode：

   ```text
   03 13 17 1b 23 33 37 3b 63 67 6f 73
   ```

4. 没有出现未实现的 `0f`。
5. 对上游 9 组 RV64I 测试做逐字节端序转换后比对，共 122 条指令全部一致：
   `registers`、`op`、`op32`、`opimm`、`opimm32`、`store`、`upperimm`、
   `environment`、`branch`。
6. `add a0, a1, a2` 的输出为 `33 85 c5 00`，对应机器码字 `0x00c58533`。

这些测试证明汇编编码和端序一致，但不能证明用户 CPU 对每个 funct3/funct7 的硬件行为
都已正确接线。后者仍需在游戏中逐类运行测试。

## 参考资料

- [Turing Complete Wiki: Spec.isa](https://turingcomplete.wiki/wiki/Spec.isa)
- [Stuffe/isa_spec](https://github.com/Stuffe/isa_spec)
- [RISC-V Unprivileged ISA 20240411](https://github.com/riscv/riscv-isa-manual/releases/tag/20240411)
- [RISC-V Assembly Programmer's Manual](https://github.com/riscv-non-isa/riscv-asm-manual)

上游 `isa_spec` 使用 MIT License，版权声明为 `Copyright 2024 LevelHead`。
