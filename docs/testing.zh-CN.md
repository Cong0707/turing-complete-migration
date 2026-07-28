# 测试与验收

## 自动化测试

```powershell
python -m unittest discover -s tests -v
```

当前 49 项测试覆盖：

- raw Snappy literal/COPY 解码、literal 编码往返和异常大小拒绝。
- 合法 v6 Custom、Program、路径段解析及 v15 转换。
- 合法 v7、v9、v10 直接枚举格式转换。
- 合法 v13/v14 单字符串、cost、immutable、linked/program、Custom 和 `u16` 导线路径。
- v9 disconnected/teleport wire 的占位降级与报告计数。
- v15 写入、反解析和元件/导线计数。
- 0.x SQLite、2.0.x 六列进度、2.1.x 四列进度和关卡别名。
- 同名方案碰撞、目标设置保留和源归档默认行为。
- 目标不存在时的准备与安装。
- 关闭归档、旧电路原件、历史电路和安装备份后无残留。
- `component_factory -> foundry` 目录映射和 Custom ID 定义闭包。
- 剧情端口省略、独立架构端口保留、完整 immutable 脚手架及基础导线双计数、OVERTURE
  分阶段派生。
- marker 对方案删除、当前电路缺失、数量变化和原件篡改的检测。
- 默认安装、回滚、Steam Auto-Cloud 门禁、显式云关闭确认和路径隔离。
- RV64I `spec.isa` 的 little-endian 设置、12 个允许的 opcode，以及每个定义严格只输出
  一条 32 位指令。
- C 编译包装器的 12 类允许 opcode、MUL/FENCE/CSR 拒绝、32 位指令长度、objdump
  解析、真实助记符解码、PC-relative 标签重建、越界跳转拒绝、工具链前缀回退、GCC
  约束和数据段链接保护。

所有二进制测试样本由测试代码构造，不包含真实用户存档或游戏资源。

按用户要求，C 编译流程没有在 Windows 本机安装或调用 RISC-V GCC。测试覆盖 Python
生成和验证逻辑；真实 GNU 交叉编译及游戏运行由用户在已有 Ubuntu 环境中验收。

另使用 2.1.277 同步的 `isa_spec` 解析器做了 ASM 往返验证：先将现有 RV64I 冒烟程序
汇编为 65 条指令、260 字节，再由 `compile_c.py` 的解码器生成助记符 ASM，最后重新
汇编；前后 260 字节逐字节相同。

## 真实存档只读验证

### 0.1059

- 主 `circuit.data`：92。
- 输入版本：v6=92。
- 源总计：1484 个元件、5330 条导线。
- 输出：92 个源方案加 6 个 OVERTURE 派生方案，共 98 个 v15。
- 150 个旧剧情边界端口不写入候选；当前 immutable 脚手架按实际 campaign 文件逐关卡计数。
- 映射质量：1403 exact、81 approximate。
- 旧存档实际使用的 90 种元件 kind 均有映射。
- RV64：23 个元件、190 条导线、16 个 Custom，转换后保持。
- Custom 闭包：34 个定义、33 个被引用 ID、派生后 189 个引用实例，0 缺失、0 重复。

### 2.0.16

- 主 `circuit.data`：231。
- 输入版本：v6=90、v7=31、v9=2、v10=108。
- 源总计：2125 个元件、5941 条导线。
- 输出：231 个 v15；每个文件转换前后元件/导线数一致。
- 映射质量：2048 exact、77 approximate。
- 319 条 disconnected wire 使用 v15 占位段并明确报告。

### 原生 v15 对照

在最新版游戏中创建的 test 方案包含 22 个元件、37 条导线，其中 19 个 8 位
`switch_word`、2 个 `on`、1 个 `decoder_3`。项目 parser 得到相同结构，证明 v15
主要字段顺序不是通过旧数据自洽猜测出来的。

## 候选验收

无目标基线、无任何保留副本的 0.1059 候选实测：

- 98 个 `circuit.data` 全为 v15。
- `verify` 为 `ok: true`，98 个状态均为 `unchanged_v15`。
- `not_gate` 候选为 1 个 NAND、5 条导线，运行时预期补回 2 个端口。
- 独立 OVERTURE/LEG/RV64 分别为 40/149、149/1446、23/190（元件/导线）。
- `overture_1_registers`～`overture_3_immediates` 的 OVERTURE 为 38 个用户元件、149 条
  导线，运行时注入 9 个 immutable 元件，预期 47 个。
- `overture_4_program`、`overture_5_conditionals`、`binary_programming` 的 OVERTURE
  同为 38/149，运行时注入 11 个 immutable 元件，预期 49 个。
- `introduction` 与 `nand_gate` 的基础电路分别含 1、3 条导线；postflight 同时接受纯用户
  导线数和运行时写回完整基础导线后的计数。
- 无 `archive/`、`_tcm_original_circuit.data`、`circuit_backup_*.data`、旧 `settings.txt`。
- 无备份安装后没有 `.tcm-backup-*`、`.tcm-replaced-*` 或 `.tcm-install-*` 残留。

## 人工游戏验收

自动验证只能证明格式、引用字段和结构数量，不证明逻辑等价。进入游戏后依次检查：

1. 关卡树与完成状态。
2. 普通小关卡的门和导线不为空。
3. Custom 元件可以展开且端口合理。
4. RV64 显示约 23 个顶层元件、190 条导线，不再是 0 门。
5. RAM/Program 加载、位宽、时序和 opcode。
6. 退出游戏后运行 `tcmigrate postflight`。

若数量仍一致但行为错误，应根据报告中的 `approximate` 元件清单进行手工适配，而不是
再次更改容器版本字节。
