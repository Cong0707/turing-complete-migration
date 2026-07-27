# 安装、复检与恢复

## 安装前门禁

- Turing Complete 必须退出。
- 目标含 `steam_autocloud.vdf` 且 Steam 正在运行时，安装会拒绝执行。
- 准备目录必须带 marker，并通过 v15 结构和数量验证。
- 源、准备目录、目标目录不能互相包含，也不能含符号链接或 junction。

## 默认安装

默认命令：

```powershell
tcmigrate install "D:\migration-output\save" "$env:APPDATA\Turing Complete" --yes
```

目标存在时：

1. 把准备目录复制到目标同级 `.tcm-install-*` 临时目录。
2. 把当前目标重命名为 `Turing Complete.tcm-backup-*`。
3. 把临时目录重命名为正式目标。

第二次重命名失败时，工具尝试恢复旧目标。

## 无备份安装

```powershell
tcmigrate install "D:\migration-output\save" "$env:APPDATA\Turing Complete" `
  --yes --no-backup
```

- 目标不存在时，候选直接就位，不创建备份。
- 目标存在时，旧目标在事务期间临时移到 `.tcm-replaced-*`；新目标成功后立即删除旧目录。
- 成功返回后，不应存在 `.tcm-backup-*`、`.tcm-replaced-*` 或 `.tcm-install-*`。

该模式没有成功安装后的自动恢复来源。重新生成候选只能依赖仍保持只读的旧源存档。

若 Steam 仍运行但已经在 Steam UI 中明确关闭本游戏云同步，可显式确认：

```powershell
tcmigrate install "D:\migration-output\save" "$env:APPDATA\Turing Complete" `
  --yes --no-backup --steam-cloud-disabled
```

该选项只记录用户确认，不会修改 Steam 设置或自行证明云开关状态。

## 默认备份的回滚

只有默认安装产生 `.tcm-backup-*` 时才能使用：

```powershell
tcmigrate rollback `
  "$env:APPDATA\Turing Complete.tcm-backup-YYYYMMDD-HHMMSS" `
  "$env:APPDATA\Turing Complete" `
  --yes
```

回滚会先把当前目标改为 `.tcm-pre-rollback-*`，因此回滚本身也保留现场。明确不需要
任何备份的用户不应使用这条流程，而应删除目标并从只读源重新 `prepare + install`。

## 游戏运行后的复检

退出游戏后执行：

```powershell
tcmigrate postflight "$env:APPDATA\Turing Complete"
```

关键状态：

- `unchanged_v15`：仍与准备结果逐字节一致。
- `rewritten_with_matching_counts`：游戏重写了文件，但 v15 可完整解析且元件/导线数量一致。
- `component or wire count mismatch`：疑似被清空或部分保存。
- `current circuit.data is version ..., expected 15`：格式意外回退或文件被替换。
- `missing current circuit.data`：方案目录或主电路丢失。

仅当准备时启用原件保留，才会出现 `_tcm_original_circuit.data` 的检查结果。

## Steam Cloud

人工验收期间建议完全退出 Steam。确认本地新存档稳定后再启动 Steam，并在冲突提示中
仔细选择本地版本。工具不会修改 Steam VDF、远端云状态或账户设置。
