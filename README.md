# GNSS_STATUSCHECK_TEST

北云 UG016 GNSS 室内→室外冷启动状态检查工具。

本项目用于分析 UG016 原始日志在室内冷启动、移动到室外、卫星恢复、时间恢复和定位恢复过程中的状态变化。工具提供 Tkinter HMI，可单选或多选数据文件；多选时每个文件都会独立生成一份完整报告，不做文件间合并对比。

---

## 1. 目录结构

```text
GNSS_STATUSCHECK_TEST/
├── 启动分析软件.py             # HMI 启动入口
├── gnss_sat_status_hmi.py      # Tkinter HMI
├── gnss_sat_status_core.py     # 主解析、绘图、报告生成
├── aux_quality.py              # GSV / INSPVAXA / KSXT 辅助解析
├── README.md
├── .gitignore
├── by_data/                    # 待分析原始日志
│   └── *.txt
├── by_manual/                  # 北云手册与接口资料
│   ├── UG016.md
│   ├── UG016_数据通信接口协议_北云科技.pdf
│   └── icom3 setup.jpg
├── Memory/                     # 本地分析记忆
│   └── *.md
└── report/                     # 自动生成的报告
    └── <数据文件名>/
        ├── report.html
        ├── satellite_status_timeline.png
        ├── coldstart_quality_diagnosis.png
        ├── age_link_audit.png
        ├── timeseries.csv
        ├── quality_timeseries.csv
        ├── gsv_satellites.csv
        └── key_events.csv
```

`by_data/`、`by_manual/`、`Memory/`、`report/` 均会随仓库保存；Git 仅排除 Python 缓存。

---

## 2. 运行方式

### 2.1 环境要求

- Python 3.10+
- matplotlib

安装依赖：

```powershell
python -m pip install matplotlib
```

### 2.2 启动 HMI

```powershell
python 启动分析软件.py
```

也可以直接运行：

```powershell
python gnss_sat_status_hmi.py
```

### 2.3 HMI 操作

1. 点击 `选择文件（可多选）` 选择一个或多个日志文件；也可以点击 `全选 by_data`。
2. 点击 `开始分析并生成报告`。
3. 分析完成后，选择是否打开 `report.html`。
4. 点击 `打开报告目录` 可打开 `report/`。

多选不会生成合并对比图。每个文件都会生成自己的独立报告目录。

---

## 3. 输入数据

输入文件为北云 UG016 原始日志，当前工具关注以下 ASCII 报文：

| 报文 | 用途 |
|---|---|
| `BESTGNSSPOSA` | 主定位源：Sol Type、Pos Type、σ、基站ID、Diff_age、Sol_age、卫星数 |
| `BESTPOSA` | 回退定位源：当日志中没有 `BESTGNSSPOSA` 时使用 |
| `INSPVAXA` | INS状态、INS位置类型、位置σ |
| `GPGSV` / `GLGSV` / `GAGSV` / `GBGSV` / `GQGSV` | 视野内卫星、仰角、方位角、SNR |
| `KSXT` | 交叉验证定位状态、定位卫星数、差分龄期、基准站卫星数 |

工具只接受校验通过的报文：

- `#` 报文使用 UG016 的 32-bit CRC
- 标准 NMEA 报文使用 8-bit XOR
- `KSXT` 按手册说明使用 32-bit CRC

校验失败的候选不会进入统计或图形。

---

## 4. 输出文件说明

### 4.1 report.html

每个数据文件只有一份 HTML 报告，所有分析内容都已合并其中：

| 章节 | 内容 |
|---|---|
| 1. 时间线图 | `#SVs`、`#solnSVs`、Pos Type、Sol Type、关键事件编号 |
| 2. 数据与解析质量 | 样本数、定位源、CRC状态、时间范围、卫星数范围 |
| 3. 关键事件 | 首次非UNKNOWN时间、首次SOL_COMPUTED、首次定位类型等 |
| 4. 状态统计 | Pos Type、Sol Type、Time Status 计数与占比 |
| 5. 字段口径与依据 | 手册字段来源和解释 |
| 6. 冷启动诊断时间线 | Time Status、卫星数、GSV SNR、σ、Diff_age、INS状态 |
| 7. AGE / 差分链路专项审计 | Diff_age、Sol_age、基站ID存在性与异常统计 |
| 8. 诊断线索 | 基于当前字段的工程判断线索 |
| 9. 行业常见原因与现有字段覆盖 | 遮挡、多径、几何、时间、差分链路、INS等方向 |

### 4.2 satellite_status_timeline.png

包含三行：

1. 跟踪卫星数与参与解算卫星数
2. Pos Type 定位状态
3. Sol Type 解算状态

关键事件在图中以编号标注。

### 4.3 coldstart_quality_diagnosis.png

包含五行：

1. Time Status：UNKNOWN / COARSE / FINESTEERING
2. `#SVs` 与 `#solnSVs`
3. GSV 逐星 SNR、有SNR卫星数、SNR≥35 dB-Hz 卫星数
4. 水平σ与 Diff_age
5. INS状态

### 4.4 age_link_audit.png

包含三行：

1. Diff_age
2. 基站ID存在性
3. Sol_age

图中 2s 和 5s 只是工程审计提示线，不是 UG016 手册限值。

### 4.5 CSV 文件

| 文件 | 内容 |
|---|---|
| `timeseries.csv` | 每条 BESTGNSSPOSA/BESTPOSA 的时间、状态、卫星数 |
| `quality_timeseries.csv` | 位置、σ、Diff_age、Sol_age、基站ID |
| `gsv_satellites.csv` | 每颗 GSV 卫星的星座、PRN、仰角、方位角、SNR |
| `key_events.csv` | 关键事件及其时间基准 |

---

## 5. 时间轴规则

### 5.1 标准GPS时间

`Time Status != UNKNOWN` 的样本直接使用标准 ASCII 头中的：

- GPS Week
- GPSec

### 5.2 UNKNOWN 时间回推

手册说明 `UNKNOWN` 表示尚未计算出准确 GPS 时间。因此 UNKNOWN 报文中的默认周数/周内秒不能当作真实绝对 GPS 时间使用。

工具采用：

1. 找到日志中最近的非 UNKNOWN GPS 时间锚点。
2. 用相邻正常递增报文估计实测输出节拍，例如 0.1 s。
3. 从锚点向 UNKNOWN 区间反向或正向回推。
4. 将这些样本放回连续时间轴上。
5. 在 CSV 中用 `time_basis` 标记。

`time_basis` 取值：

| 值 | 含义 |
|---|---|
| `GPS标准时间` | 直接来自报文头 GPS Week / GPSec |
| `锚点回推` | 由非UNKNOWN锚点按输出节拍回推 |

回推时间只用于时间轴展示，不表示接收机已经获得准确 GPS 时间。

---

## 6. 核心字段口径

以下字段含义均依据 `by_manual/UG016.md`。

### 6.1 BESTGNSSPOSA 4.2.2

| 手册字段 | 名称 | 含义 | 单位 |
|---:|---|---|---|
| 2 | Sol Type | 解算状态 | - |
| 3 | Pos Type | 定位状态 | - |
| 4 | Lat | 纬度 | ° |
| 5 | Lon | 经度 | ° |
| 6 | Hgt | 海拔高 | m |
| 7 | Undulation | 高程异常 | m |
| 8 | Datum ID | 坐标系ID | - |
| 9 | Lat σ | 纬度标准差 | m |
| 10 | Lon σ | 经度标准差 | m |
| 11 | Hgt σ | 高度标准差 | m |
| 12 | Stn ID | 基准站ID | - |
| 13 | Diff_age | 差分延迟时间 | s |
| 14 | Sol_age | 解算延迟时间 | s |
| 15 | `#SVs` | 跟踪卫星数 | 颗 |
| 16 | `#solnSVs` | 参与解算卫星数 | 颗 |
| 17 | `#solnL1SVs` | L1/E1/B1 解算卫星数 | 颗 |
| 18 | `#solnMultiSVs` | 多频解算卫星数 | 颗 |

本工具主图只使用：

- `#SVs`
- `#solnSVs`

`#solnL1SVs` 与 `#solnMultiSVs` 只导出到 CSV，不混入主图卫星数。

### 6.2 标准ASCII头 2.1.2.1

| 字段 | 含义 |
|---:|---|
| 6 Time Status | UNKNOWN / COARSE / FINESTEERING |
| 7 GPS Week | GPS周数 |
| 8 GPSec | GPS周内秒，精确到ms |

### 6.3 表4-1 Sol Type

常用值：

| 值 | 含义 |
|---|---|
| `SOL_COMPUTED` | 完全解算 |
| `INSUFFICIENT_OBS` | 观测量不足 |
| `VARIANCE` | 方差超过限值 |
| `NO_CONVERGENCE` | 不收敛 |
| `COLD_START` | 冷启动尚未完全解算 |

### 6.4 表4-2 Pos Type

常用值：

| 值 | 含义 |
|---|---|
| `NONE` | 未解算 |
| `SINGLE` | 单点解 |
| `PSRDIFF` | 伪距差分 |
| `L1_FLOAT` | L1浮点解 |
| `IONOFREE_FLOAT` | 无电离层浮点解 |
| `NARROW_FLOAT` | 窄带浮点解 |
| `L1_INT` | L1固定解 |
| `WIDE_INT` | 宽带固定解 |
| `NARROW_INT` | 窄带固定解 |

### 6.5 表4-8 INS状态

常用值：

| 值 | 含义 |
|---|---|
| `INS_INACTIVE` | 对准未激活 |
| `INS_ALIGNING` | 正在进行粗对准 |
| `INS_SOLUTION_GOOD` | 对准完成结果较好 |
| `INS_SOLUTION_FREE` | 卫星结果较差不可用 |
| `INS_ALIGNMENT_COMPLETE` | 粗对准完成 |
| `WAITING_INITIALPOS` | 等待位置解 |
| `WAITING_AZIMUTH` | 等待航向角 |

### 6.6 GSV 4.1.8

| 字段 | 含义 |
|---:|---|
| 2 | GSV消息总数 |
| 3 | 当前GSV消息序号 |
| 4 | 视野内卫星数 |
| 5 | 卫星号 |
| 6 | 仰角，° |
| 7 | 方位角，° |
| 8 | SNR |

GSV 每条消息最多传输 4 颗卫星，不足 4 颗时用空字段填充。工具只把有有效 PRN 的条目解析为卫星，空槽不计入卫星数。

### 6.7 KSXT 4.4.3

| 字段 | 含义 |
|---:|---|
| 11 | 卫星定位状态：0未定位，1单点，2RTK浮点，3RTK固定 |
| 14 | 定位天线当前参与解算的卫星数量 |
| 21 | 差分龄期 |
| 22 | 基准站卫星数 |

---

## 7. 分析解释边界

- `#SVs` 是跟踪卫星数，不等于可见卫星数。
- GSV 的视野内卫星数与 `#SVs` 是不同口径。
- `#solnSVs` 是参与解算卫星数，是本工具的核心卫星数量指标。
- `Sol Type` 和 `Pos Type` 是两个字段，不能混用。
- σ 是接收机自估计精度，不是实测误差。
- SNR、卫星数变化不能唯一区分遮挡、多径和天线/前端问题。
- 基站ID和 Diff_age 存在只能说明接收机记录到差分数据龄期，不能证明 RTK 模糊度可用。
- 当前日志没有 GSA/GST/DOP 类报文时，无法量化几何精度因子或伪距残差。
- 当前日志没有 TRACKSTATA 时，无法分析逐通道 C/N0、locktime 和跟踪状态。
- GSV 缺少自身 GPS 周/周内秒字段，报告中 GSV 时间采用同一完整批次前最近 `BESTGNSSPOSA` 头时间，属于顺序近似。
- 图中 AGE 的 2s/5s 线只是工程审计提示线，不是手册限值。
- UNKNOWN 时间回推是工程时间轴重建方法，不是 UG016 手册规定的官方算法。

---

## 8. 当前示例数据结论

仓库中的 `by_data/` 包含三份示例日志。

### 8.1 0703002-0918-11-09

| 指标 | 结果 |
|---|---:|
| 样本数 | 3776 |
| Time Status | 全程 `FINESTEERING` |
| Pos Type | 全程 `SINGLE` |
| Sol Type | 全程 `SOL_COMPUTED` |
| `#SVs` | 24~32 |
| `#solnSVs` | 11~20 |
| 基站ID | `1793` |
| Diff_age | 0.7~6.7 s，中位 1.4 s |
| `>5s` 样本 | 25 |
| 差分/浮点/固定 | 无 |

判断：

- 已有足够卫星和稳定单点解。
- 记录到基站ID和差分龄期。
- 但没有进入 `PSRDIFF`、浮点或固定解。
- 优先排查基站改正内容、RTK配置、RTCM消息类型与频点匹配。

### 8.2 0703002-0918-15-32

| 指标 | 结果 |
|---|---:|
| 样本数 | 11954 |
| GPS标准时间样本 | 7016 |
| UNKNOWN回推样本 | 4938 |
| Time Status | `UNKNOWN` 后进入 `COARSE` |
| Pos Type | 全程 `NONE` |
| Sol Type | `INSUFFICIENT_OBS` / `VARIANCE` |
| `#SVs` | 0~8 |
| `#solnSVs` | 0 |
| 基站ID | 空 |
| Diff_age | 0 |
| 定位 | 无 |

判断：

- 典型室内冷启动失败数据。
- 前半段没有准确GPS时间。
- 后半段仅得到 `COARSE`。
- 跟踪到少量卫星，但参与解算数始终为0。
- 无有效差分基准站证据。
- 无定位、无差分、无RTK。

### 8.3 0703002-0918-15-42

| 指标 | 结果 |
|---|---:|
| 样本数 | 4360 |
| Time Status | 全程 `FINESTEERING` |
| Pos Type | 4355条 `SINGLE`，5条 `NONE` |
| Sol Type | 全程 `SOL_COMPUTED` |
| `#SVs` | 17~26 |
| `#solnSVs` | 0~19 |
| 基站ID | `1793` |
| Diff_age | 0~3.8 s，中位 1.4 s |
| `>5s` 样本 | 0 |
| 差分/浮点/固定 | 无 |

判断：

- 大部分时间已有稳定单点解。
- 有基站ID和差分龄期。
- 但仍没有进入差分、浮点或固定解。
- 优先排查差分改正与RTK配置。

---

## 9. 常见问题

### 9.1 为什么多选后没有生成对比图？

这是有意设计。多选只是批量分析，每个文件都生成独立报告，避免不同文件的状态和口径被误读为同一时间线。

### 9.2 为什么 UNKNOWN 数据没有丢弃？

UNKNOWN 表示尚未计算出准确 GPS 时间，但传感器状态、卫星数和解算失败原因仍然有价值。工具保留这些样本，并使用锚点回推将其放到连续时间轴上，同时明确标记 `锚点回推`。

### 9.3 为什么没有 DOP？

当前日志未录制 GSA/GST/DOP 类报文，因此不能计算或推断 DOP。

### 9.4 为什么没有逐通道 locktime？

当前日志未录制 `TRACKSTATA`。如果后续录制该报文，可进一步分析逐通道跟踪状态、C/N0 和 locktime。

### 9.5 为什么报告中有多个卫星数量？

因为它们口径不同：

- `#SVs`：跟踪卫星数
- `#solnSVs`：参与解算卫星数
- GSV视野内卫星数：接收机报告的视野内卫星口径

三者不能互相替代。

---

## 10. 许可与数据说明

代码用于工程日志分析。手册、原始日志和报告请遵守相应供应商和项目数据使用限制。
