# 存档与电路格式笔记

本文记录工具实际实现的 v6、v7、v9、v10、v15 电路格式。结论优先来自真实运行数据，
并与 `Stuffe/save_monger` 的公开历史实现交叉验证。

## 根目录

| 游戏版本 | Windows 存档根目录 | 进度索引 |
| --- | --- | --- |
| 0.1059 | `%APPDATA%\Godot\app_userdata\Turing Complete_backup` | `progress.dat` SQLite |
| 2.0.16 | `%APPDATA%\Godot\app_userdata\Turing Complete` | `_progress.dat`、六列 `levels.txt` |
| 2.1.278 | `%APPDATA%\Turing Complete` | 四列 `levels.txt`，游戏会自行生成其他状态文件 |

电路通常位于：

```text
schematics/<关卡>/<方案>/circuit.data
schematics/architecture/<架构>/circuit.data
schematics/component_factory/<分类>/<元件>/circuit.data   # 旧版
schematics/foundry/<分类>/<元件>/circuit.data             # 2.1.x 实际索引
```

## 外层容器

所有已支持版本均为：

```text
+0x00  u8              保存格式版本
+0x01  raw Snappy      版本专属未压缩结构
```

这里是 raw Snappy，不是 framed Snappy。项目实现标准 literal/COPY 解码；写出时使用合法
的 literal-only raw Snappy 编码。压缩率不是协议要求，最新版可以正常解码。

## v6 结构

v6 头部按顺序为：

```text
i64 save_id
u32 hub_id
i64 gate
i64 delay
bool menu_visible
u32 clock_speed
sequence<i64> dependencies       # u16 数量
string description               # u16 字节长度，Nim 原始字符串
point<i16, i16> camera_position
u8 sync_state
bool campaign_bound
u16 score
bytes player_data                # u16 字节长度
string hub_description
i64 component_count
component[component_count]
i64 wire_count
wire[wire_count]
```

普通 v6 元件：

```text
u16 legacy_kind
point<i16, i16> position
u8 rotation
i64 permanent_id
string custom_string_or_label
u64 setting_1
u64 setting_2
i16 ui_order
```

附加字段：

- `legacy_kind == 92 (Custom)`：`i64 custom_id`、`point displacement`。
- `legacy_kind in {64, 68, 94}`：`u16 count`，随后是 `i64 key + string program`。

v6 导线：

```text
u8 legacy_wire_kind
u8 color
string comment
point start
u8 segment ...                   # 高 3 位方向，低 5 位长度，0 终止
```

## 已确认的 v6 加载失败根因

0.1059 的旧枚举使用 `92 = Custom`，当前枚举使用 `92 = com_time`，当前的
`Custom = 78`。最新版读取 v6 时按照新枚举判断 kind，因此遇到旧 92 不会读取后面的
`custom_id + displacement`。下一个字段从错误偏移开始，随后元件、导线计数和内容均可能
失真。游戏最终会把失败结果保存成很小的 v15 空电路。

所以仅改变外层版本字节或原样复制 v6 都不可行，必须用旧枚举解析后重新编码。

## v7、v9、v10

这三版已经使用与 v15 兼容的主体枚举，工具不做枚举替换，只解析代际字段差异：

- 头部 clock speed 已为 `u64`，仍包含已废弃 camera position。
- v7 元件含废弃 parent permanent ID；Custom 和部分特殊元件有各自附加表。
- v9 开始统一使用 linked components 与 selected programs。
- v10 的 linked component 比 v9 多 offset。
- 导线路径仍是 v6 风格的一字节段。

v6-v12 不保存 v13+ 的 512 字节 Custom design。工具输出零 design，但不会丢弃
Custom ID、依赖关系或元件主体。2.1.x 从 `schematics/foundry/` 加载定义时会执行：

```text
add_custom_prototype
  -> reload_custom_prototype
  -> update_custom_design
```

`update_custom_design` 扫描 Custom 定义内的元件布局并重建设计区域。因此关键要求是把
旧 `component_factory` 目录映射到 `foundry`；若仍留在旧目录，定义根本不会进入上述
加载链，引用实例会在方案保存时被删除。

## v15 结构

v15 头部移除了 camera/campaign-bound，clock speed 为 `u64`。当 circuit custom ID
非零时，头部后包含固定 512 字节 custom design。

v15 元件主体包括：

- `u16 kind`、位置、旋转、永久 ID；
- user label、custom string；
- `sequence<u64> settings`、buffer size、UI order、word size；
- immutable、gate/delay cost、endianness、init data；
- linked components；
- selected programs；
- Custom 专属 custom ID 与 custom word sizes。

v15 导线不再保存旧 wire kind，路径段改为 `u16`：高 3 位方向、低 13 位长度，0 终止。

工具写出 v15 后立即完整反解析，并核对元件数和导线数。容器可解压但字段尾随、截断、
计数错位或路径段非法都不会通过验证。

### 2.1.278 剧情端口注入

当前剧情关卡会把游戏目录 `campaign/<level>/circuit.data` 中的 immutable level input/output
与用户方案合并，并在保存时把合并结果写回。0.1059 用户方案本身也包含同一组旧端口，
直接转换会得到重叠的两组端口。`not_gate` 的实测变化为 3 个旧元件加载后变成 5 个：
NAND 不变，输入和输出各重复一次；随后测试编译器报 `Output does not have property _is_z`。

迁移器在明确属于当前 combinational/sequential campaign 的方案中省略 level interface
元件，但完整保留连接导线。报告分别记录 `output_component_count`（启动前）和
`runtime_component_count`（游戏补回端口后）。独立 `schematics/architecture/` 不参与
campaign 合并，因此必须保留自己的架构输入输出。

## 无法原样表示的字段

### disconnected / teleport wire

旧一字节路径以 `0x20` 表示“起点和终点不连续”，后面直接存 finish point。v15 没有
对应编码。工具镜像公开当前实现的降级行为，写成从起点向东一格的占位段 `(0, 1)`，
并增加 `teleport_wire_approximation_count`。

### Program key

v6 的 Program 选择表以数字关卡 ID 为键，v15 使用字符串。工具把数字无损转成十进制
字符串，例如 `86 -> "86"`，不在没有运行时证据时猜测新版关卡名称。

### 元件替代

旧 RAM/ROM/Program 变体、寄存器变体、旧显示、三态/双向 IO、声音、网络等可能没有
完全等价的新元件。映射表为每类标记 `exact`、`approximate`、`placeholder` 或
`deleted`，报告会列出受影响数量和说明。

## 真实数据验证

- 0.1059：92 个源主电路全为 v6；另派生 6 个 OVERTURE 剧情方案，正式目标为 98 个
  v15。150 个剧情边界端口改由运行时注入，所有导线保留。
- 2.0.16：v6=90、v7=31、v9=2、v10=108；2125 个元件、5941 条导线，逐文件计数一致。
- 0.1059 RV64：23 个元件、190 条导线、16 个 Custom；转换后保持。
- 原生 2.1.276 测试电路：22 个元件、37 条导线，可由本项目 v15 parser 完整读取。
- 0.1059 自定义元件闭包：34 个 foundry 定义，33 个被引用 ID；加入派生方案后 189 个引用实例，
  缺失和重复 ID 均为 0。

这些结果证明结构转换没有把电路清空，但不证明所有替代元件在游戏中的逻辑行为等价。
