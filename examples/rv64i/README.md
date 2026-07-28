# Turing Complete RV64I `spec.isa`

这里提供一份面向 Turing Complete 2.1.278 的 RV64I 基础整数指令集规格：

- 成品：`spec.isa`
- 编译冒烟测试：`smoke-test.asm`
- 完整说明：[`../../docs/rv64i-spec.zh-CN.md`](../../docs/rv64i-spec.zh-CN.md)

把 `spec.isa` 放到目标架构电路目录，与 `circuit.data` 同级。用户当前 RV64 的位置为：

```text
%APPDATA%\Turing Complete\schematics\architecture\RV64\spec.isa
```

此文件不会修改电路，也不会补充 CPU 尚未实现的硬件行为。它只负责把汇编语句编码成
RV64I 机器码。

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

用户提供的 GCC/objdump/二进制写入脚本属于旧版流程，本示例没有把它迁移成新版写入
工具。该流程目前只用于确认 `-march=rv64i` 和 little-endian 字节顺序；新版程序导入
方式留待后续单独设计。

## 来源和许可

此规格改编自 MIT 许可的
[`Stuffe/isa_spec`](https://github.com/Stuffe/isa_spec) RV64I 规格，基线提交为
`24f317bc207d933f659d01404a070ed6ed867d61`；该提交与 Turing Complete 2.1.277
同步，语法也已用同版本解析器验证。
