# 北云 UG016 GNSS 室内→室外冷启动分析

## 用途

分析北云 UG016 原始日志中室内冷启动到室外恢复过程的：

- 跟踪卫星数 `#SVs`
- 参与解算卫星数 `#solnSVs`
- 解算状态 `Sol Type`
- 定位状态 `Pos Type`
- 时间状态 `Time Status`
- GSV 逐卫星仰角、方位角、SNR
- 接收机自估计位置 σ
- 差分龄期 `Diff_age`
- 解算延迟 `Sol_age`
- 基站 ID
- INS 状态

每个数据文件都会生成一份完全独立的完整报告，不做文件间合并对比。

## 运行方式

1. 双击 `启动分析软件.bat`，或执行：
   ```powershell
   python 启动分析软件.py
   ```
2. 点击“全选 by_data”，或手动选择一份/多份数据文件。
3. 点击“开始分析并生成报告”。

多选时，每个文件分别生成一个独立报告目录。

## 输出内容

每个数据文件的报告目录中包含：

- `report.html`
  - 唯一 HTML 报告
  - 包含卫星数、定位状态、解算状态、关键事件、冷启动诊断、AGE/差分链路审计、诊断线索和字段依据
- `satellite_status_timeline.png`
- `coldstart_quality_diagnosis.png`
- `age_link_audit.png`
- `timeseries.csv`
- `quality_timeseries.csv`
- `gsv_satellites.csv`
- `key_events.csv`

## 时间轴规则

- `Time Status != UNKNOWN` 的报文直接使用标准 ASCII 头中的：
  - GPS Week
  - GPSec
- `UNKNOWN` 报文的原始默认周数/周内秒不用于绝对时间定位。
- `UNKNOWN` 报文以最近非 UNKNOWN GPS 时间锚点为基准，按实测输出节拍回推/前推。
- CSV 中使用 `time_basis` 标记：
  - `GPS标准时间`
  - `锚点回推`

回推时间只用于时间轴展示，不表示接收机已经获得准确 GPS 时间。

## 字段口径（依据 `by_manual/UG016.md`）

### BESTGNSSPOSA 4.2.2

| 字段 | 含义 |
|---|---|
| 2 `Sol Type` | 解算状态 |
| 3 `Pos Type` | 定位状态 |
| 9 Lat σ | 纬度标准差，m |
| 10 Lon σ | 经度标准差，m |
| 11 Hgt σ | 高度标准差，m |
| 12 Stn ID | 基站ID |
| 13 Diff_age | 差分延迟时间，s |
| 14 Sol_age | 解算延迟时间，s |
| 15 `#SVs` | 跟踪卫星数 |
| 16 `#solnSVs` | 参与解算卫星数 |
| 17 `#solnL1SVs` | L1/E1/B1 解算卫星数 |
| 18 `#solnMultiSVs` | 多频解算卫星数 |

### 标准ASCII头 2.1.2.1

| 字段 | 含义 |
|---|---|
| 6 Time Status | UNKNOWN / COARSE / FINESTEERING |
| 7 GPS Week | GPS周数 |
| 8 GPSec | GPS周内秒 |

### 表4-1 解算状态

例如：

- `SOL_COMPUTED`
- `INSUFFICIENT_OBS`
- `VARIANCE`

### 表4-2 定位状态

例如：

- `SINGLE`
- `PSRDIFF`
- `L1_FLOAT`
- `NARROW_FLOAT`
- `L1_INT`
- `NARROW_INT`

### 表4-8 INS状态

例如：

- `INS_INACTIVE`
- `WAITING_AZIMUTH`
- `INS_SOLUTION_FREE`
- `INS_ALIGNMENT_COMPLETE`

### GSV 4.1.8

| 字段 | 含义 |
|---|---|
| 2 | GSV消息总数 |
| 3 | 当前GSV消息序号 |
| 4 | 视野内卫星数 |
| 5 | 卫星号 |
| 6 | 仰角，度 |
| 7 | 方位角，度 |
| 8 | SNR |

## 解释边界

- `#SVs` 是跟踪卫星数，不等于可见卫星数；GSV 的视野内卫星数是另一个口径。
- `#solnSVs` 是参与解算卫星数，是本工具的核心卫星数量指标。
- `#solnL1SVs` 和 `#solnMultiSVs` 仅导出，不混入主图卫星数。
- GSV 缺少自身 GPS 周/周内秒字段，报告中 GSV 时间采用同一完整批次前最近 `BESTGNSSPOSA` 头时间，属于顺序近似。
- σ 是接收机自估计精度，不是实测误差。
- SNR、卫星数变化不能唯一区分遮挡、多径和天线/前端问题，只能作为排查线索。
- 当前日志没有 GSA/GST/DOP 类报文，因此不能量化几何精度因子或伪距残差。
- `TRACKSTATA` 未录制；如果能录制，它可提供逐通道 C/N0、locktime 和跟踪状态，对定位失败根因分析更有价值。
- 图中 AGE 的 2s/5s 线只是工程审计提示线，不是 UG016 手册限值。
- 所有报文均要求校验通过；校验失败的候选不进入统计。

## 依赖

- Python 3
- matplotlib

## 目录约定

- `by_data/`：待分析原始数据
- `by_manual/`：北云数据手册
- `report/`：生成的报告
- `Memory/`：本地分析记忆
