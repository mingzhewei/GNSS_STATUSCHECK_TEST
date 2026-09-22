# UG016 GNSS 状态检查分析范式（2026-09-22）

## 固定分析口径

- 主定位源优先使用 `BESTGNSSPOSA`；仅当不存在时回退 `BESTPOSA`。
- `#SVs` = 跟踪卫星数。
- `#solnSVs` = 参与解算卫星数，是核心指标。
- `#solnL1SVs`、`#solnMultiSVs` 仅作为导出字段，不混入主图卫星数量。
- `Sol Type` 与 `Pos Type` 是两个不同字段，必须分开展示。
- `Time Status` 使用 UG016 2.1.2.1 释义：
  - UNKNOWN：尚未计算出准确GPS时间
  - COARSE：粗时间
  - FINESTEERING：精细时间
- 多选文件时，每个文件独立生成一份完整报告，不做文件间合并对比。
- 每个报告只保留一份 `report.html`，冷启动诊断、AGE审计和诊断线索全部合并其中。
- 原 `coldstart_diagnosis.html` 不再生成。

## 时间轴规则

- 非 UNKNOWN 样本直接使用标准头 GPS Week / GPSec。
- UNKNOWN 样本的原始默认周/周内秒不用于绝对时间定位。
- UNKNOWN 样本以最近非 UNKNOWN GPS 锚点为基准，按实测输出节拍回推/前推。
- CSV 中 `time_basis` 标记：
  - `GPS标准时间`
  - `锚点回推`

## AGE / 差分链路审计

报告必须包含：

- `Diff_age`
- `Sol_age`
- `Stn ID`
- `Diff_age` 最小值、中位数、P95、最大值
- `>2s`、`>5s`、`>10s` 样本数
- 基站ID为空样本数
- AGE/差分链路结论

注意：

- 2s/5s 是工程审计提示线，不是手册限值。
- 基站ID和Diff_age存在只能说明接收机记录到差分数据龄期，不能证明RTK模糊度可用。
- `KSXT` 可用于交叉验证定位状态、参与解算卫星数、差分龄期和基准站卫星数。

## 本项目三份数据的关键结论

### 0703002-0918-11-09

- 样本：3776
- 时间状态：全程 FINESTEERING
- Pos Type：全程 SINGLE
- Sol Type：全程 SOL_COMPUTED
- `#SVs`：24~32
- `#solnSVs`：11~20
- 基站ID：1793
- Diff_age：0.7~6.7 s，中位 1.4 s，25条>5s
- 无 PSRDIFF / 浮点 / 固定

### 0703002-0918-15-32

- 样本：11954
- GPS标准时间样本：7016
- UNKNOWN回推样本：4938
- 时间状态：UNKNOWN 后进入 COARSE
- Pos Type：全程 NONE
- Sol Type：INSUFFICIENT_OBS / VARIANCE
- `#SVs`：0~8
- `#solnSVs`：0
- 基站ID：空
- Diff_age：0
- 无定位，无差分，无RTK
- 这是典型室内冷启动失败数据

### 0703002-0918-15-42

- 样本：4360
- 时间状态：全程 FINESTEERING
- Pos Type：4355条 SINGLE，5条 NONE
- Sol Type：全程 SOL_COMPUTED
- `#SVs`：17~26
- `#solnSVs`：0~19
- 基站ID：1793
- Diff_age：0~3.8 s，中位 1.4 s，无>5s
- 无 PSRDIFF / 浮点 / 固定

## 工程判断

- `11-09` 和 `15-42` 有基站ID、非零Diff_age和可用单点解，但始终未进入差分或RTK解，优先排查基站改正内容、RTK配置/授权、RTCM消息类型与频点匹配、基准站坐标/天线信息。
- `15-32` 失败发生在更早阶段：时间未完全恢复、卫星跟踪弱、无有效基站ID、无参与解算卫星。
- 三份日志都没有 RTK浮点或固定证据。
- 当前日志无 GSA/GST/DOP/TRACKSTAT，不能量化几何因子或逐通道锁定质量。

## 本次最终代码入口

- HMI：`gnss_sat_status_hmi.py`
- 启动器：`启动分析软件.py`
- 启动脚本：`启动分析软件.bat`
- 核心解析与报告：`gnss_sat_status_core.py`
- 扩展质量解析：`aux_quality.py`
