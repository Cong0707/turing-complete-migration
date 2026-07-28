# Turing Complete 存档迁移工具

把《图灵完备》0.1059 或 2.0.16 的旧存档迁移到当前 2.1.x 存档格式。

本项目不会把旧 `circuit.data` 原样交给最新版游戏。它会按旧格式解析每个电路，显式
处理 v6 的旧元件枚举，再写出可以由 2.1.278 直接读取的完整 v15 电路容器。

## 当前能力

- 输入电路版本：v6、v7、v9、v10、v13、v14、v15。
- 输出电路版本：统一为 v15。
- 保留用户元件、全部导线、位置、旋转、永久 ID、位宽、Custom ID、Program 选择、
  linked components 及已识别设置；剧情边界端口由新版运行时注入，不重复写入用户方案。
- 将旧 `schematics/component_factory/` 映射到最新版实际索引的
  `schematics/foundry/`，并验证所有 Custom ID 的定义闭包。
- 迁移 0.x SQLite 或 2.0.x 六列 `levels.txt` 中可证明对应的剧情进度。
- 把 0.1059 的全局 OVERTURE 架构派生到新版五个分阶段关卡和
  `binary_programming`，同时保留沙盒使用的独立架构。
- 支持最新版目标存档已经存在，也支持 `%APPDATA%\Turing Complete` 尚未创建。
- 默认提供私密源归档、逐电路原件和安装备份；也可以通过明确的 `--no-*` 选项完全不留。
- 安装前和游戏运行后都完整解析 v15，并核对每个导入方案的元件/导线数量。
- 无第三方运行时依赖，使用 Python 3.10 及以上。

源存档始终只读。`prepare` 只写新的输出目录；只有 `install` 会写最新版目标目录。

## 为什么需要直接转换

0.1059 的 v6 使用旧元件枚举，其中旧 `Custom = 92`。当前枚举的 `92` 已变成
`com_time`。最新版 v6 loader 因此不会读取旧 Custom 后面的 `custom_id` 和位移字段，
后续字节流整体错位，最终可能把复杂 CPU 重写为空电路。

本工具绕过这条损坏路径：旧枚举解析 → 显式元件映射 → v15 写入 → v15 反解析验证。

2.1.278 的剧情关卡还会把自带 `campaign/<level>/circuit.data` 中的 immutable 脚手架
合并进用户方案。若旧端口也被迁入，画面会出现两套端口，测试编译器可能绑定到错误的
`Output` 并报 `_is_z` 缺失。工具因此只在剧情副本中省略旧边界端口，保留连接导线；
独立 `architecture/` 方案仍保留自己的端口。报告从实际 v13/v14 campaign 电路计算
完整运行时脚手架数量，不再假定运行时只补两个端口。

## 安装

Windows PowerShell：

```powershell
git clone git@github.com:Cong0707/turing-complete-migration.git
cd turing-complete-migration
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
tcmigrate
```

不安装也可以运行：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m turing_complete_migration
```

不带参数时进入中文交互菜单。

## 推荐流程

1. 退出 Turing Complete。若目标已有 `steam_autocloud.vdf`，安装时也退出 Steam。
2. 运行 `tcmigrate`，选择 0.1059、2.0.16 或自定义源路径。
3. 执行“准备迁移”，检查 `migration-report.json` 中的转换和降级统计。
4. 执行“验证迁移目录”，必须得到 `ok: true`。
5. 安装候选，启动最新版，先检查小关卡，再检查 Custom，最后检查 CPU。
6. 退出游戏后运行 `postflight`；元件或导线数量不符会被明确报告。

默认安全模式会保留恢复材料。若你明确不需要任何备份，可以使用：

```powershell
tcmigrate prepare `
  "$env:APPDATA\Godot\app_userdata\Turing Complete_backup" `
  "$env:APPDATA\Turing Complete" `
  "D:\migration-output" `
  --game-dir "D:\Game\Steam\steamapps\common\Turing Complete" `
  --no-archive --no-preserve-original --no-circuit-backups

tcmigrate install `
  "D:\migration-output\save" `
  "$env:APPDATA\Turing Complete" `
  --yes --no-backup
```

这些 `--no-*` 选项是不可逆偏好：安装成功后不会留下 `.tcm-backup-*`，准备目录中也
没有旧电路原件或完整源归档。源存档本身仍不会被修改。

## 命令行

```powershell
tcmigrate inspect "C:\path\to\save"
tcmigrate prepare "C:\old" "C:\current" "D:\migration-output" --game-dir "D:\Game\Turing Complete"
tcmigrate verify "D:\migration-output\save"
tcmigrate install "D:\migration-output\save" "%APPDATA%\Turing Complete" --yes
tcmigrate postflight "%APPDATA%\Turing Complete"
tcmigrate rollback "%APPDATA%\Turing Complete.tcm-backup-..." "%APPDATA%\Turing Complete" --yes
```

准备选项：

- `--no-archive`：不创建 `output/archive/source`。
- `--no-preserve-original`：不创建 `_tcm_original_circuit.data`。
- `--no-circuit-backups`：不导入旧 `circuit_backup_*.data`。

安装选项：

- `--no-backup`：替换目标时不留下 `.tcm-backup-*`。
- `--steam-cloud-disabled`：Steam 仍运行时，明确确认已经关闭本游戏的 Steam Cloud。

## 已验证数据

- 0.1059：92 个源主电路全部转换；另从全局 OVERTURE 派生 6 个新版剧情方案，正式目标
  共 98 个 v15。剧情副本省略 150 个由运行时注入的边界端口，导线全部保留。
- 2.0.16：231/231 个主电路转换成功，版本分布为 v6=90、v7=31、v9=2、v10=108；
  共 2125 个元件、5941 条导线，逐文件计数一致。
- 真实 0.1059 RV64：23 个元件、190 条导线，其中 16 个 Custom；写成 v15 后计数保持。
- 派生 OVERTURE：阶段 1～3 为 38 个用户元件加 9 个 immutable 脚手架，运行时 47 个；
  阶段 4～5 与 `binary_programming` 加 11 个，运行时 49 个。
- 自定义元件：34 个 foundry 定义覆盖全部 33 个被引用 ID；派生 OVERTURE 后报告中共有
  189 个 Custom 引用实例，缺失/重复 ID 为 0。
- 自动化测试：35 项，测试数据均由代码生成，不含用户存档。

## 不可自动消除的差异

- 81 个 0.1059 元件实例需要语义近似；主要涉及旧 RAM/Program、寄存器变体、显示、
  三态/双向 IO 和已经删除的元件。
- v7/v9/v10 的 disconnected/teleport wire 在 v15 中没有对应表示，工具按官方当前行为
  写成从起点向东一格的占位段，并在报告中计数。
- 旧 Program 的数字关卡键会无损保留为十进制字符串，例如 `86 -> "86"`；运行时是否
  需要按新版关卡 ID 再映射，必须通过游戏人工验证。
- v6-v12 不保存当前 512 字节 Custom design。工具写零 design；最新版从 foundry
  载入定义时会调用 `reload_custom_prototype -> update_custom_design`，按元件布局重建。
- 物理尺寸、端口位置、内存时序和 opcode 的变化仍可能要求手工重新布线或调整程序。
- 派生到新版分阶段关卡的 OVERTURE 是可见、可编辑的兼容起点；新版不可编辑脚手架、
  Program/RAM 和测试目标变化很大，不能保证直接通过关卡。
- “数量一致”证明电路没有被清空，不等于跨版本逻辑完全等价。

## 输出与隐私

默认输出：

```text
migration-output-.../
  migration-report.json
  save/
  archive/source/             # 可用 --no-archive 关闭
  archive/manifest.json
```

完整存档中的 `settings.txt` 可能包含个性化令牌。不要把存档、私密归档或未经检查的报告
上传到 GitHub、论坛或 issue。

## 文档

- `docs/format-notes.zh-CN.md`：v6/v7/v9/v10/v13/v14/v15 字段与根因。
- `docs/migration-strategy.zh-CN.md`：迁移、碰撞、进度与降级策略。
- `docs/report-format.zh-CN.md`：tool format 2 报告和 marker。
- `docs/testing.zh-CN.md`：自动化及真实存档验证结果。
- `docs/recovery.zh-CN.md`：有备份和无备份两种安装方式。
- `docs/development.zh-CN.md`：继续开发格式支持的方法。
- `docs/rv64i-spec.zh-CN.md`：与用户 RV64 CPU 的 12 个 opcode 组匹配的
  little-endian `spec.isa`、覆盖范围和验证结果。
- `docs/rv64i-c-toolchain.zh-CN.md`：从 freestanding C 编译、链接并生成最新版可用
  `U32` `.assembly` 的流程和 Harvard 数据段限制。

独立成品位于 `examples/rv64i/spec.isa`，C 编译工具位于
`examples/rv64i/c-toolchain/`。它们不会由迁移命令自动写入存档。

## 许可证

项目代码使用 MIT License。格式研究参考了 CC0 的 `Stuffe/save_monger` 和其 MIT
许可的 SuperSnappy 依赖；RV64I 示例改编自 MIT 许可的 `Stuffe/isa_spec`。本仓库
不包含游戏文件、用户存档或提取出的游戏源码。

本项目是社区工具，与 Turing Complete 开发者和发行方无关。
