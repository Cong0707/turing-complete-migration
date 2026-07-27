# 报告与 Marker 格式

当前 `tool_format` 为 `2`。

## migration-report.json

主要顶层字段：

- `operation_id`、`created_utc`：迁移标识与时间。
- `source`：只读源检查结果。
- `target_before`：已有目标的检查结果；目标不存在时为 `null`。
- `target_existed`：准备时目标是否存在。
- `archive_source`、`preserve_original`、`include_circuit_backups`：实际保留策略。
- `settings_policy`、`binary_policy`：本次处理规则的文字说明。
- `progress`：进度读取、映射、跳过和输出统计。
- `verification`：准备结束后的 v15 结构验证。

### schematics

- `converted_unit_count`：转换的主方案数。
- `source_version_counts`：v6/v7/v9/v10/v13/v14/v15 输入分布。
- `mapping_quality_counts`：`exact`、`approximate`、`placeholder` 等实例数量。
- `teleport_wire_approximation_count`：无法原样写入 v15 的 disconnected wire 数量。
- `converted_circuit_backup_count` / `omitted_circuit_backup_count`：旧历史电路处理结果。
- `imported_units[]`：每个方案的源、目标、容器元数据和详细 conversion。
- `derived_architecture_units`：从旧全局架构派生到当前剧情关卡的方案。
- `skipped_architecture_derivations`：因已有目标方案而跳过的派生请求。
- `custom_dependency_audit`：foundry 定义数、引用 ID/实例数、缺失或重复定义、零 design
  定义清单以及实际定义目录。

每个 `conversion` 至少包含：

```text
source_version
output_version
source_component_count
output_component_count
runtime_component_count
runtime_injected_component_count       # 有当前 campaign 基础电路时
runtime_campaign_source_version        # 基础电路外层版本
runtime_campaign_component_count       # 基础电路总元件数
runtime_campaign_wire_count            # 基础电路总导线数
stripped_level_interface_count
stripped_level_interface_kind_counts
source_wire_count
output_wire_count
runtime_injected_wire_count            # 有当前 campaign 基础电路时
runtime_wire_count                     # 有当前 campaign 基础电路时
mapping_quality_counts
replacements
custom_component_count
selected_program_entry_count
teleport_wire_approximation_count
verified_v15
```

## save/.turing-complete-migration.json

marker 随候选一起安装。`imported_units[]` 对每个方案记录：

- `unit`：相对 `schematics/` 的安全路径。
- `source_circuit`：源版本、大小、解压大小、SHA-256。
- `converted_circuit`：准备时 v15 的相同容器元数据。
- `conversion`：期望输出元件/导线数量及降级信息。
- `original_preserved`：是否应存在 `_tcm_original_circuit.data`。

## verify / postflight

`imported_circuits[]` 的正常状态：

- `unchanged_v15`
- `rewritten_with_matching_counts`

其他状态均使 `ok` 为 false。验证不会只依赖解压成功；它会调用 v15 parser 并比较
实际元件/导线数量。未运行的候选使用 output 计数；游戏注入 immutable 剧情脚手架后
允许使用 runtime 计数。runtime 元件数来自当前 `campaign/<level>/circuit.data` 的
immutable 元件，runtime 导线数用于兼容运行时把基础导线一并写回的情况。

`preserved_original_pairs[]` 只为 `original_preserved=true` 的方案生成。正常状态为
`preserved`。

## 隐私

报告不包含 `settings.txt` 的值，但包含本机绝对路径、方案名、文件哈希和元件统计。
发布 issue 前仍应人工检查。`archive/source/` 和其中的 manifest 永远视为私密数据。
