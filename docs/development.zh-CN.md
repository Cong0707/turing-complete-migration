# 开发指南

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

Python 3.10+，无第三方运行时依赖。

## 模块

- `snappy.py`：raw Snappy 编解码和容器检查。
- `legacy_v6.py`：v6/v7/v9/v10/v13/v14 解析、旧元件映射、v15 写入和反解析。
- `saves.py`：存档代际检查、SQLite 完整性、树哈希和进程门禁。
- `progress.py`：三代进度读取、关卡别名和当前 `levels.txt` 写入。
- `migration.py`：准备、转换、marker、验证、安装、回滚和 postflight。
- `cli.py`：中文交互菜单和自动化子命令。

## 内部模型

`legacy_v6.py` 使用两个层次：

- `LegacyCircuit/LegacyComponent/LegacyWire`：仅表示 v6 旧枚举和附加字段。
- `CurrentCircuit/CurrentComponent/CurrentWire`：表示可写入 v15 的统一结构。

v7/v9/v10/v13/v14 已经使用当前主体枚举，直接解析进 `CurrentCircuit`。任何新版本支持都应先
进入统一模型，再由唯一的 `write_v15()` 输出。

旧 `component_factory` 必须在迁移层映射到 `foundry`。`custom_dependency_audit` 应继续
保证所有被引用 Custom ID 都有唯一的 foundry 定义；不要把目录兼容问题塞进二进制 parser。

## 新增元件映射

1. 从真实旧文件和公开历史实现确认旧 kind 的字段。
2. 在 `LEGACY_KIND_NAMES` 中命名。
3. 在 `COMPONENT_MAP` 中指定当前 kind、word size、quality 和 note。
4. 必要时在 `_component_settings()` 或 `convert_component()` 中处理专属字段。
5. 增加生成式二进制 fixture，验证位置、ID、设置和报告。
6. 在真实副本上确认逐文件元件/导线计数不变。

不要为了让统计好看而把近似映射标成 exact。

## 新增保存版本

最低要求：

- 字段顺序有公开代码、反汇编或原生样本交叉证据。
- parser 拒绝截断、异常计数和尾随字节。
- 至少一个最小合法样本和一个特有字段样本。
- 写 v15 后反解析，比较关键字段和计数。
- 真实数据批量验证，不把用户样本提交仓库。

## 字符串

Nim 历史格式存的是原始字节。项目使用 UTF-8 `surrogateescape`，以便无法解码的旧
Program 元数据仍能逐字节往返。不要改成默认 replacement decoding。

## 安装事务

默认备份和 `--no-backup` 都先复制并验证临时目录。无备份模式只允许在成功安装后删除
旧目标，失败路径必须尽量恢复。Windows 上 SQLite 连接必须用 `contextlib.closing` 真正
关闭，否则目录重命名会被文件句柄阻止。

## 发布检查

- 运行全部测试和 `py_compile`。
- 扫描 `circuit.data`、`settings.txt`、SQLite、token、绝对用户路径和缓存。
- 仓库不得包含真实存档、迁移输出、`.egg-info`、`__pycache__` 或游戏资源。
- 更新中英文 README、changelog、format notes 和论坛草稿。
