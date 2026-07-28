# Turing Complete RV64I `spec.isa`

这里提供一份面向 Turing Complete 2.1.278 的 RV64I 基础整数指令集规格：

- 成品：`spec.isa`
- 编译冒烟测试：`smoke-test.asm`
- C 编译流程：`c-toolchain/`
- 完整说明：[`../../docs/rv64i-spec.zh-CN.md`](../../docs/rv64i-spec.zh-CN.md)
- C 编译说明：[`../../docs/rv64i-c-toolchain.zh-CN.md`](../../docs/rv64i-c-toolchain.zh-CN.md)

把 `spec.isa` 放到目标架构电路目录，与 `circuit.data` 同级。用户当前 RV64 的位置为：

```text
%APPDATA%\Turing Complete\schematics\architecture\RV64\spec.isa
```

此文件不会修改电路，也不会补充 CPU 尚未实现的硬件行为。它只负责把汇编语句编码成
RV64I 机器码。

## 从 C 生成程序

在已有 GNU RISC-V bare-metal 工具链的 Ubuntu 环境中：

```bash
cd examples/rv64i/c-toolchain
sh build.sh example.c -o example.asm
```

流程会把 freestanding C 编译、链接，再把最终机器码反解为可直接复制到游戏程序编辑器
的 RV64I 助记符和标签。当前版本只输出代码，遇到全局数据、字符串、
`.rodata/.data/.bss` 会直接失败，原因是当前 Harvard 架构尚无已确认的数据 RAM 自动
装载流程。

## 覆盖范围

覆盖以下 12 个 opcode 组：

```text
OP, OP-IMM, LOAD, STORE, BRANCH, LUI, AUIPC,
JAL, JALR, SYSTEM, OP-IMM-32, OP-32
```

不包含 `MISC-MEM/FENCE`、CSR、乘除法、原子、浮点、压缩或向量扩展。

## 端序

规格使用：

```text
endianness = little
```

这是为了匹配当前 RV64 电路中 8 位字宽的指令存储器，以及已有程序采用的标准
RISC-V little-endian 字节顺序。例如：

```text
add a0, a1, a2
```

机器码字是 `0x00c58533`，写入字节流后为：

```text
33 85 c5 00
```

## 注意

为了避免 `spec.isa` 对一个长输出整体进行端序翻转，本规格只让每个定义输出一条
32 位指令。因此没有加入会展开成两条或更多机器指令的 `call`、`tail`、`lla`、
完整 32/64 位 `li` 等伪指令。

`li` 仍可用于 `-2048..2047` 的单条 `ADDI` 形式。更大的常量请手工使用
`lui`/`addi` 组合。

规格把 `;`、`//` 和 `#` 都配置为汇编源码的行注释。

用户提供的旧版 GCC 参数和 little-endian 二进制流程已整理为独立的
`c-toolchain/compile_c.py`。新版不再生成旧版逐字节粘贴文本，而是生成当前汇编器可直接
输入的 RV64I 助记符 `.asm` 文件；工具不会写入存档。

## 来源和许可

此规格改编自 MIT 许可的
[`Stuffe/isa_spec`](https://github.com/Stuffe/isa_spec) RV64I 规格，基线提交为
`24f317bc207d933f659d01404a070ed6ed867d61`；该提交与 Turing Complete 2.1.277
同步，语法也已用同版本解析器验证。
