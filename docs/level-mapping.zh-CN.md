# 关卡进度映射

迁移工具只把“能证明是同一关卡或明确替代关系”的旧完成状态写入 2.1.278。
同名且仍存在的关卡直接保留；改名关卡使用下表。旧分数不迁移。

| 旧 ID | 2.1.278 ID | 依据 |
| --- | --- | --- |
| `crude_awakening` | `introduction` | 同一开场关卡，标题和剧情一致 |
| `component_factory` | `foundry` | 工具关卡及说明文字一致 |
| `decoder1` | `decoder_1` | 1-bit decoder 改名 |
| `decoder3` | `decoder_3` | 3-bit decoder 改名 |
| `byte_less` | `byte_less_u` | 无符号比较任务一致 |
| `byte_less_i` | `byte_less_s` | 有符号比较任务一致 |
| `byte_shift` | `byte_lsr` | alpha 分支把旧移位教学替换为当前移位关卡 |
| `alu_1` | `overture_alu_1` | Overture ALU 第一阶段 |
| `alu_2` | `overture_alu_2` | Overture ALU 第二阶段 |
| `conditions` | `overture_conditions` | 条件位任务一致 |
| `decoder` | `overture_decoder` | Overture 指令解码任务一致 |
| `registers` | `overture_1_registers` | Overture 寄存器阶段 |
| `constants` | `overture_3_immediates` | 立即数阶段及说明文字一致 |
| `program` | `overture_4_program` | Program/RAM 取指阶段一致 |
| `turing_complete` | `overture_5_conditionals` | 条件跳转和 Turing Complete 结局一致 |
| `sorter` | `sort` | Delicious Order 排序任务一致 |
| `ai_showdown` | `nim` | 12 张牌、每次取 1～3 张的对局规则一致 |

旧 Overture 流程把 `registers`、`constants`、`program`、`turing_complete` 的工作直接
保存在全局 `architecture/OVERTURE`。新版把它拆为五个关卡。工具会把该全局架构派生到
`overture_1_registers`～`overture_5_conditionals`，并根据已到达后续阶段的证据补出
`overture_2_alu` 行；派生结果是兼容起点，不代表能直接通过新版测试。

## 0.1059 实测结果

实测数据库有 75 行，其中 70 行完成。以 2.1.278 的 `campaign/` 过滤并应用上表后：

- 最终 `levels.txt` 有 61 行；新增的一行是有后续完成证据的 `overture_2_alu`。
- 15 个旧 ID 因已删除或无法证明等价而跳过：
  `wide_instructions`、`stack`、`spacial_invasion`、`computing_codes`、
  `tick_tock`、`leg_1`～`leg_4`、`byte_or`、`ram`、`test_lab`、
  `unseen_fruit`、`compute_xor`、`delay_level`。
- 跳过只影响新版进度索引。对应 `schematics/` 方案仍会转换；私密归档是否存在取决于
  是否启用 `--no-archive`。

尤其没有把旧 `ram`、`stack` 或 `leg_*` 直接标记成新的 Symphony 关卡。它们在概念上
相似，但电路架构和任务已经显著改变，直接标完成会跳过新版必须进行的人工适配。

## 2.0.16 实测结果

该存档的实际 6 列 `levels.txt` 只有 3 行：`crude_awakening`、
`component_factory`、`sandbox`。工具优先读取该文件而不是残留 SQLite，并保留其中的
当前方案名。它适合提供已经经历部分 alpha 转换的电路候选，但不能替代 0.1059 的
完整剧情进度。

## 扩展映射的要求

新增映射至少应提供一种可复查证据：

- 当前关卡资源中相同的任务说明或测试逻辑；
- 官方 wiki 的明确改名/替代记录；
- 游戏运行时迁移结果；
- 可重复的电路和进度行为对照。

仅凭标题相似或“看起来像下一关”不足以写入默认映射。
