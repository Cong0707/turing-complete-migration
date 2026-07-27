# 迁移策略

## 数据流

```text
只读旧存档
  -> 识别每个 circuit.data 的实际版本
  -> v6 旧枚举解析 / v7-v10 直接枚举解析
  -> 统一 CurrentCircuit 内存模型
  -> 写出 v15
  -> 反解析 v15 并核对元件、导线数量
  -> 合并可证明的进度
  -> 写入独立候选目录
  -> 人工确认后安装
```

不再依赖最新版游戏的 v6 逐版 loader。该 loader 的枚举错位正是 Custom 电路被清空的
根因。

## 源、目标和输出

- 源目录永不修改。
- 目标存在时，先复制它作为新版基线，保留新版设置和用户内容。
- 目标不存在时，创建最小候选，只写转换后的 `schematics/`、`levels.txt` 和 marker；
  `settings.txt` 等由最新版首次启动自行生成。
- 同名方案若目标已存在，旧方案复制为 `[legacy <标签>]`，不静默覆盖。
- 旧 `component_factory` 必须映射为当前 `foundry`；分类和元件名等内部路径保持不变。
- 准备阶段收集每个 Custom 定义的 circuit custom ID 和全部引用 ID。缺失定义或一个 ID
  对应多个定义时拒绝生成候选。

## 保留策略

公开工具采用安全默认：

- `archive/source/`：完整私密源归档。
- `_tcm_original_circuit.data`：每个迁移方案的源电路字节。
- `circuit_backup_*.data`：导入时也转换为 v15。
- 安装时 `.tcm-backup-*`：目标整目录备份。

用户可以分别关闭：

```text
--no-archive
--no-preserve-original
--no-circuit-backups
--no-backup
```

关闭后不保留对应材料。无备份安装仍使用同卷临时目录：若目标已存在，旧目标只在替换
事务中暂时改名；新目标成功就位后立即删除。若删除或安装失败，工具尽量恢复旧目标，
但成功返回后不留下恢复副本。

## v6 元件映射

映射遵循以下优先级：

1. 当前存在且语义、位宽一致：`exact`。
2. 当前元件合并了旧变体或端口/时序变化：`approximate`。
3. 没有直接等价物，只能保留可见占位：`placeholder`。
4. 已废弃且无法合理表示：`deleted`。

报告记录旧 kind、名称、数量、目标 kind、目标位宽和说明。工具不会隐瞒语义降级。

Custom 位置执行旧版公开转换规则：

```text
new_position = old_position + old_displacement + (15, 15)
```

Custom dependency 由转换后所有非零 custom ID 重新计算。

v6-v12 没有当前 512 字节 design。定义写入 foundry 后，2.1.x 的
`reload_custom_prototype` 会调用 `update_custom_design` 按定义内部布局重建；不能把定义
留在旧 `component_factory` 目录等待游戏猜测。

## 进度迁移

- 0.x 从 `progress.dat` 读取。
- 2.0.x 优先读取六列 `levels.txt`，避免使用更旧的 SQLite 残留。
- 目标进度写为四列当前格式。
- 只迁移当前 campaign 中仍存在或具有明确别名证据的关卡。
- 旧 gate/delay/tick 分数不迁移，因为规则已经变化。
- 当前方案名只有在对应 v15 电路实际存在时才写入。

完整关卡表见 `level-mapping.zh-CN.md`。

## 验证标准

对 marker 中每个导入方案检查：

1. `circuit.data` 存在且 raw Snappy 容器有效。
2. 外层版本必须为 15。
3. v15 字段必须完整解析到流末尾。
4. 元件数与转换报告的 output component count 一致。
5. 导线数与转换报告的 output wire count 一致。
6. 游戏未改写时 SHA-256 与准备结果一致；游戏正常重写但数量一致时允许哈希变化。
7. 仅当 marker 声明保留原件时，检查 `_tcm_original_circuit.data` 的存在和哈希。

`postflight` 报告数量不符、格式回退、文件缺失或原件损坏。它不会把“哈希变化但结构
数量一致”误判为失败。

## 人工验收顺序

1. 检查主菜单和关卡解锁。
2. 打开一个含少量基础门的小关卡。
3. 打开普通 Custom 元件。
4. 打开 CPU 架构，确认门数量和布线非零。
5. 运行简单程序，重点检查 RAM/Program、位宽、端口位置和 opcode。
6. 退出游戏后运行 `postflight`。

结构计数通过后，剩余工作属于跨版本电路适配，而不是存档容器恢复。
