# -*- coding: utf-8 -*-
"""北云 UG016 GNSS 卫星数与状态时间线分析核心模块。

所有字段口径均来自本目录 by_manual/UG016.md：
- 2.1.2.1 标准ASCII头：Time Status / GPS Week / GPSec
- 4.2.2 BESTGNSSPOS：字段15 #SVs，字段16 #solnSVs，字段17/18 L1与多频解算卫星数
- 表4-1 解算状态 Sol Type
- 表4-2 定位状态 Pos Type
"""

from __future__ import annotations

import csv
import html
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aux_quality import parse_aux, summarize_quality, AuxData

HASH_ANCHORS = (b"#BESTGNSSPOSA,", b"#BESTPOSA,")
PRIMARY_SOURCE = "BESTGNSSPOSA"
FALLBACK_SOURCE = "BESTPOSA"

POSITION_TYPE_DESCRIPTIONS = {
    "NONE": "未解算", "FIXEDPOS": "位置已由FIX POSITION命令固定",
    "FIXEDHEIGHT": "位置已由FIX HEIGHT或FIX AUTO命令固定",
    "FLOATCONV": "浮点载波相位模糊解", "WIDELANE": "宽巷模糊解",
    "NARROWLANE": "窄巷模糊解", "DOPPLER_VELOCITY": "使用瞬时多普勒计算速度",
    "SINGLE": "单点解", "PSRDIFF": "伪距差分", "WAAS": "SBAS解",
    "PROPAGATED": "卡尔曼滤波器无新观测推算解", "L1_FLOAT": "L1浮点解",
    "IONOFREE_FLOAT": "无电离层浮点解", "NARROW_FLOAT": "窄带浮点解",
    "L1_INT": "L1固定解", "WIDE_INT": "宽带固定解", "NARROW_INT": "窄带固定解",
    "RTK_DIRECT_INS": "RTK直接通过INS初始化", "INS_SBAS": "天线校正后INS位置",
    "INS_PSRSP": "INS伪距单点解-没有DGPS校正", "INS_PSRDIFF": "INS伪距差分",
    "INS_RTKFLOAT": "INS RTK浮点解", "INS_RTKFIXED": "INS RTK固定解",
    "PPP_CONVERGING": "正在进行精密单点定位（TerraStar-C）解算",
    "PPP": "精密单点定位（TerraStar-C）",
    "OPERATIONAL": "精度在UAL范围内", "WARNING": "精度在UAL范围外但在警告范围内",
    "OUT_OF_BOUNDS": "解的精度在UAL极限之外",
    "INS_PPP_Converging": "正在进行INS PPP解（TerraStar-C）",
    "INS_PPP": "INS PPP解（TerraStar-C）",
    "PPP_BASIC_CONVERGING": "正在进行精密单点定位（TerraStar-L）解算",
    "PPP_BASIC": "精密单点定位（TerraStar-L）",
    "INS_PPPP_BASIC_Converging": "正在进行INS PPP解（TerraStar-L）",
    "INS_PPPP_BASIC": "INS PPP解（TerraStar-L）",
}
POSITION_TYPE_GROUPS = {
    "NONE": "无解", "FIXEDPOS": "固定输入位置", "FIXEDHEIGHT": "固定输入高程",
    "FLOATCONV": "浮点", "WIDELANE": "浮点", "NARROWLANE": "浮点",
    "DOPPLER_VELOCITY": "多普勒速度", "SINGLE": "单点", "PSRDIFF": "伪距差分",
    "WAAS": "SBAS", "PROPAGATED": "推算", "L1_FLOAT": "浮点",
    "IONOFREE_FLOAT": "浮点", "NARROW_FLOAT": "浮点", "L1_INT": "固定",
    "WIDE_INT": "固定", "NARROW_INT": "固定", "RTK_DIRECT_INS": "RTK/INS",
    "INS_SBAS": "INS/SBAS", "INS_PSRSP": "INS单点", "INS_PSRDIFF": "INS伪距差分",
    "INS_RTKFLOAT": "INS RTK浮点", "INS_RTKFIXED": "INS RTK固定",
    "PPP_CONVERGING": "PPP", "PPP": "PPP", "OPERATIONAL": "UAL状态",
    "WARNING": "UAL状态", "OUT_OF_BOUNDS": "UAL状态",
    "INS_PPP_Converging": "INS PPP", "INS_PPP": "INS PPP",
    "PPP_BASIC_CONVERGING": "PPP", "PPP_BASIC": "PPP",
    "INS_PPPP_BASIC_Converging": "INS PPP", "INS_PPPP_BASIC": "INS PPP",
}
SOLUTION_STATUS_DESCRIPTIONS = {
    "SOL_COMPUTED": "完全解算", "INSUFFICIENT_OBS": "观测量不足",
    "NO_CONVERGENCE": "不收敛", "SINGULARITY": "参数矩阵异常",
    "COV_TRACE": "协方差超过最大值（>1000米）", "TEST_DIST": "测试距离超限",
    "COLD_START": "冷启动尚未完全解算", "V_H_LIMIT": "高度或速度超过限值",
    "VARIANCE": "方差超过限值", "RESIDUALS": "残差过大",
    "INTEGRITY_WARNING": "残差过大使定位不可靠", "PENDING": "FIX位置待验证",
    "INVALID_FIX": "FIX位置命令输入的位置无效", "UNAUTHORIZED": "定位类型未经授权",
    "INVALID_RATE": "此解决方案类型不支持所选的输出速率",
}
MAJOR_POSITION_TYPES = {
    "SINGLE", "PSRDIFF", "WAAS", "PROPAGATED", "FLOATCONV", "WIDELANE",
    "NARROWLANE", "L1_FLOAT", "IONOFREE_FLOAT", "NARROW_FLOAT", "L1_INT",
    "WIDE_INT", "NARROW_INT", "RTK_DIRECT_INS", "INS_SBAS", "INS_PSRSP",
    "INS_PSRDIFF", "INS_RTKFLOAT", "INS_RTKFIXED", "PPP_CONVERGING", "PPP",
    "INS_PPP_Converging", "INS_PPP", "PPP_BASIC_CONVERGING", "PPP_BASIC",
    "INS_PPPP_BASIC_Converging", "INS_PPPP_BASIC",
}


def crc32_manual(payload: bytes) -> int:
    crc = 0
    for b in payload:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc & 0xFFFFFFFF


def format_gps_time(week: int, tow: float) -> str:
    return f"GPS {week}周 {tow:.3f}s"


def pos_label(name: str) -> str:
    desc = POSITION_TYPE_DESCRIPTIONS.get(name)
    group = POSITION_TYPE_GROUPS.get(name, "未在映射表")
    return f"{name}｜{desc or '未在手册映射表'}｜{group}"


def sol_label(name: str) -> str:
    desc = SOLUTION_STATUS_DESCRIPTIONS.get(name)
    return f"{name}｜{desc or '未在手册映射表'}"


@dataclass
class PositionSample:
    t: float
    week: int
    tow: float
    time_status: str
    sol_status: str
    pos_type: str
    tracked: int
    used: int
    l1: int
    multi: int
    multi: int
    source: str
    header_week: int = 0
    header_tow: float = 0.0
    time_basis: str = "GPS标准时间"


@dataclass
class KeyEvent:
    event_id: int
    label: str
    t: float
    week: int
    tow: float
    detail: str
    major: bool
    sample: PositionSample | None = None

@dataclass
class FileAnalysis:
    path: Path
    label: str
    source: str = ""
    samples: list[PositionSample] = field(default_factory=list)
    all_samples: list[PositionSample] = field(default_factory=list)
    message_counts: Counter = field(default_factory=Counter)
    bad_crc_counts: Counter = field(default_factory=Counter)
    malformed_count: int = 0
    unknown_time_count: int = 0
    median_period_s: float | None = None
    gap_threshold_s: float | None = None
    time_jump_count: int = 0
    gap_count: int = 0
    events: list[KeyEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.samples)

    @property
    def start(self) -> PositionSample | None:
        return self.samples[0] if self.samples else None

    @property
    def end(self) -> PositionSample | None:
        return self.samples[-1] if self.samples else None

    @property
    def duration_s(self) -> float:
        return self.end.t - self.start.t if self.start and self.end else 0.0

# ---------------------------------------------------------------------------
# 报文提取与解析
# ---------------------------------------------------------------------------

def _iter_ascii_lines(path: Path):
    """流式按CR/LF切行；数据文件含二进制片段，仅在行内含目标锚点时产出。"""
    anchors = HASH_ANCHORS
    pending = b""
    with path.open("rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            parts = re.split(b"\r\n|\r|\n", pending + chunk)
            pending = parts.pop()
            for line in parts:
                if any(a in line for a in anchors):
                    yield line
            positions = [pending.find(a) for a in anchors if a in pending]
            if positions:
                pending = pending[min(positions):]
            else:
                pending = b""
    if pending and any(a in pending for a in anchors):
        yield pending


def _parse_hash_line(line: bytes):
    starts = [line.find(a) for a in HASH_ANCHORS]
    starts = [x for x in starts if x >= 0]
    if not starts:
        return None
    candidate = line[min(starts):].rstrip(b"\r\n")
    star = candidate.rfind(b"*")
    if star <= 0:
        return None
    try:
        checksum = int(candidate[star + 1:star + 9], 16)
    except ValueError:
        return None
    if crc32_manual(candidate[1:star]) != checksum:
        return None
    try:
        text = candidate[1:star].decode("ascii", "strict")
    except UnicodeDecodeError:
        return None
    if ";" not in text:
        return None
    header, body = text.split(";", 1)
    hf, bf = header.split(","), body.split(",")
    return hf[0], hf, bf


def _parse_position_message(name: str, hf: list[str], bf: list[str]):
    try:
        week, tow = int(hf[5]), float(hf[6])
        if not (0 <= tow < 604800.0):
            return None
        return PositionSample(
            t=week * 604800.0 + tow, week=week, tow=tow,
            time_status=hf[4].strip(), sol_status=bf[0].strip(),
            pos_type=bf[1].strip(), tracked=int(bf[13]), used=int(bf[14]),
            l1=int(bf[15]), multi=int(bf[16]), source=name,
            header_week=week, header_tow=tow,
        )
    except (ValueError, IndexError):
        return None

def analyze_file(path: str | Path, label: str | None = None) -> FileAnalysis:
    path = Path(path)
    result = FileAnalysis(path=path, label=label or path.stem)
    candidates: dict[str, list[PositionSample]] = {PRIMARY_SOURCE: [], FALLBACK_SOURCE: []}
    for raw in _iter_ascii_lines(path):
        anchor = "BESTGNSSPOSA" if b"#BESTGNSSPOSA," in raw else "BESTPOSA"
        parsed = _parse_hash_line(raw)
        if parsed is None:
            result.bad_crc_counts[anchor] += 1
            continue
        name, hf, bf = parsed
        result.message_counts[name] += 1
        sample = _parse_position_message(name, hf, bf)
        if sample is None:
            result.malformed_count += 1
            continue
        candidates[name].append(sample)

    if candidates[PRIMARY_SOURCE]:
        result.source = PRIMARY_SOURCE
        result.all_samples = candidates[PRIMARY_SOURCE]
    elif candidates[FALLBACK_SOURCE]:
        result.source = FALLBACK_SOURCE
        result.all_samples = candidates[FALLBACK_SOURCE]
    else:
        raise ValueError(f"未找到CRC校验通过且可解析的BESTGNSSPOSA/BESTPOSA报文：{path.name}")

    result.samples = [s for s in result.all_samples if s.time_status.upper() != "UNKNOWN"]
    # 时间轴策略：
    # 1. 非UNKNOWN样本直接使用标准头GPS周/周内秒。
    # 2. UNKNOWN样本不使用其默认周/周内秒绝对值，而是以最近非UNKNOWN锚点和实测输出节拍回推/前推。
    # 3. 回推时间仅用于时间轴位置，报告中明确标记，不冒充已确认GPS时间。
    result.samples = result.all_samples
    known_idx = [i for i, s in enumerate(result.samples) if s.time_status.upper() != "UNKNOWN"]
    result.unknown_time_count = len(result.samples) - len(known_idx)
    result.confirmed_time_count = len(known_idx)
    result.extrapolated_time_count = result.unknown_time_count
    if not known_idx:
        raise ValueError(f"{path.name} 全部目标报文时间状态为UNKNOWN，无法建立可信GPS时间轴。")
    result.time_anchor = result.samples[known_idx[0]]

    # 用同段内正常递增的原始头时间估计输出节拍，跳过默认周到真实周之间的巨大跳变。
    raw_dts = [b.header_tow + b.header_week*604800.0 - (a.header_tow + a.header_week*604800.0)
               for a, b in zip(result.samples, result.samples[1:])
               if 0 < (b.header_tow + b.header_week*604800.0 - (a.header_tow + a.header_week*604800.0)) <= 1.0]
    if not raw_dts:
        raise ValueError(f"{path.name} 无法估计报文输出节拍，不能安全回推UNKNOWN时间。")
    period = statistics.median(raw_dts)
    result.median_period_s = period
    result.gap_threshold_s = max(period * 5.0, 0.001)

    known_set = set(known_idx)
    for i, s in enumerate(result.samples):
        if i in known_set:
            s.t = s.header_week * 604800.0 + s.header_tow
            s.week = s.header_week
            s.tow = s.header_tow
            s.time_basis = "GPS标准时间"
            continue
        prev_i = max((k for k in known_idx if k < i), default=None)
        next_i = min((k for k in known_idx if k > i), default=None)
        if prev_i is not None:
            ref = result.samples[prev_i]
            dt = (i - prev_i) * period
            s.t = ref.t + dt
            total = ref.week * 604800.0 + ref.tow + dt
            week, tow = divmod(total, 604800.0)
            s.week = int(week); s.tow = tow
        elif next_i is not None:
            ref = result.samples[next_i]
            dt = (next_i - i) * period
            s.t = ref.t - dt
            total = ref.week * 604800.0 + ref.tow - dt
            if total < 0:
                raise ValueError(f"{path.name} UNKNOWN时间回推越过GPS周0，无法建立时间轴。")
            week, tow = divmod(total, 604800.0)
            s.week = int(week); s.tow = tow
        else:
            raise AssertionError("unreachable")
        s.time_basis = "锚点回推"

    for a, b in zip(result.samples, result.samples[1:]):
        dt = b.t - a.t
        if dt < -1e-9:
            result.time_jump_count += 1
        elif dt > result.gap_threshold_s:
            result.gap_count += 1

    if result.unknown_time_count:
        result.warnings.append(
            f"{result.unknown_time_count}条UNKNOWN时间样本已纳入时间轴，但时间位置由最近非UNKNOWN GPS锚点按实测输出节拍回推/前推，报告中标记为“锚点回推”；其原始默认GPS周/周内秒不用于绝对定位。"
        )
    if result.time_jump_count:
        result.warnings.append(f"检测到{result.time_jump_count}次GPS时间回跳/周跳；保留原始顺序，不做平滑或重排。")
    if result.gap_count:
        result.warnings.append(f"检测到{result.gap_count}个大于5倍中位周期的数据间隔；图中断线，不虚构连续状态。")
    if result.bad_crc_counts.total():
        result.warnings.append(f"目标报文CRC失败候选{result.bad_crc_counts.total()}条，已全部排除。")
    if result.malformed_count:
        result.warnings.append(f"CRC通过但字段不足/数值异常的目标报文{result.malformed_count}条，未进入统计。")
    if result.source == FALLBACK_SOURCE:
        result.warnings.append("未找到BESTGNSSPOSA，已使用UG016 4.2.1 BESTPOSA作为回退定位源。")

    _build_events(result)
    return result


# ---------------------------------------------------------------------------
# 关键事件
# ---------------------------------------------------------------------------

def _first(samples, predicate: Callable[[PositionSample], bool]):
    for s in samples:
        if predicate(s):
            return s
    return None


def _event(result: FileAnalysis, sample: PositionSample, label: str, detail: str, major: bool):
    result.events.append(KeyEvent(
        0, label, sample.t, sample.week, sample.tow, detail, major, sample,
    ))


def _build_events(result: FileAnalysis):
    samples = result.samples
    if not samples:
        return
    first_time = result.time_anchor

    _event(result, first_time, f"首个非UNKNOWN时间状态：{first_time.time_status}", "UG016 2.1.2.1标准ASCII头字段6；其后的UNKNOWN样本按锚点回推。", True)

    for status in ("COARSE", "FINESTEERING"):

        s = _first(samples, lambda x, status=status: x.time_status.upper() == status)
        if s:
            _event(result, s, f"首次时间状态{status}", "UG016 2.1.2.1标准ASCII头字段6。", status == "FINESTEERING")
    s = _first(samples, lambda x: x.used > 0)
    if s:
        _event(result, s, f"首次解算卫星数>0（#solnSVs={s.used}）", "UG016 4.2.2字段16 #solnSVs。", True)
    s = _first(samples, lambda x: x.sol_status == "SOL_COMPUTED")
    if s:
        _event(result, s, "首次SOL_COMPUTED", "UG016表4-1：完全解算。", True)

    seen = set()
    for s in samples:
        if s.pos_type in seen:
            continue
        seen.add(s.pos_type)
        _event(result, s, f"首次定位类型{ s.pos_type}", f"UG016表4-2：{POSITION_TYPE_DESCRIPTIONS.get(s.pos_type, '未在映射表')}；#SVs={s.tracked}，#solnSVs={s.used}。", s.pos_type in MAJOR_POSITION_TYPES or s.pos_type not in POSITION_TYPE_DESCRIPTIONS)
    seen = set()
    for s in samples:
        if s.sol_status in seen:
            continue
        seen.add(s.sol_status)
        if s.sol_status == "SOL_COMPUTED":
            continue
        _event(result, s, f"首次解算状态{s.sol_status}", f"UG016表4-1：{SOLUTION_STATUS_DESCRIPTIONS.get(s.sol_status, '未在映射表')}。", False)
    result.events.sort(key=lambda e: (e.t, e.label))
    for i, e in enumerate(result.events, 1):
        e.event_id = i

# ---------------------------------------------------------------------------
# 绘图
# ---------------------------------------------------------------------------

def _break_gaps(xs, ys, threshold):
    ox, oy = [], []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if i and threshold is not None:
            dt = x - xs[i - 1]
            if dt < -1e-9 or dt > threshold:
                ox.append(xs[i - 1] + 1e-6)
                oy.append(float("nan"))
        ox.append(x); oy.append(y)
    return ox, oy


def _origin(analyses, x_mode):
    if x_mode == "per_file":
        return {a.label: a.samples[0].t for a in analyses if a.samples}
    origin = min(a.samples[0].t for a in analyses if a.samples)
    return {a.label: origin for a in analyses}


def plot_timeline(analyses: Sequence[FileAnalysis], output_png: Path, x_mode="absolute") -> Path:
    if not analyses:
        raise ValueError("没有可绘制的数据。")
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    origins = _origin(analyses, x_mode)
    colors = plt.get_cmap("tab10").colors

    fig, axes = plt.subplots(3, 1, figsize=(20, 12.5), dpi=180,
                             gridspec_kw={"height_ratios": [1.30, 1.15, 0.85], "hspace": 0.34})
    ax_sat, ax_pos, ax_sol = axes

    for i, a in enumerate(analyses):
        c = colors[i % len(colors)]
        xs = [s.t - origins[a.label] for s in a.samples]
        xt = [float(s.tracked) for s in a.samples]
        xu = [float(s.used) for s in a.samples]
        x1, y1 = _break_gaps(xs, xt, a.gap_threshold_s)
        x2, y2 = _break_gaps(xs, xu, a.gap_threshold_s)
        ax_sat.plot(x1, y1, color=c, lw=2.5, drawstyle="steps-post", label=f"{a.label}｜#SVs")
        ax_sat.plot(x2, y2, color=c, lw=2.1, ls="--", drawstyle="steps-post", label=f"{a.label}｜#solnSVs")
    ax_sat.set_title("卫星数量时间线：#SVs跟踪卫星数（实线）与#solnSVs解算卫星数（虚线）", fontsize=17, pad=12)
    ax_sat.set_ylabel("卫星数（颗）", fontsize=13)
    ax_sat.grid(alpha=.28); ax_sat.tick_params(labelsize=11)
    ax_sat.legend(fontsize=9, ncol=min(4, len(analyses)*2), framealpha=.94)

    pos_order = []
    for a in analyses:
        for s in a.samples:
            if s.pos_type not in pos_order:
                pos_order.append(s.pos_type)
    pos_y = {v: i + 1 for i, v in enumerate(pos_order)}
    for i, a in enumerate(analyses):
        c = colors[i % len(colors)]
        xs = [s.t - origins[a.label] for s in a.samples]
        ys = [pos_y[s.pos_type] for s in a.samples]
        x, y = _break_gaps(xs, ys, a.gap_threshold_s)
        ax_pos.plot(x, y, color=c, lw=2.4, drawstyle="steps-post", label=a.label)
    # 事件点放在对应定位类型的y值上。
    for i, a in enumerate(analyses):
        c = colors[i % len(colors)]
        pos_by_t = {s.t: s.pos_type for s in a.samples}
        for e in a.events:
            if not e.major:
                continue
            x = e.t - origins[a.label]
            y = pos_y.get(pos_by_t.get(e.t, ""), len(pos_order) + .55)
            ax_pos.scatter([x], [y], s=62, facecolor="white", edgecolor=c, lw=2.1, zorder=6)
            ax_pos.annotate(str(e.event_id), (x, y), xytext=(0, 9), textcoords="offset points",
                            ha="center", fontsize=9, color=c, fontweight="bold", zorder=7)
    ax_pos.set_yticks([pos_y[v] for v in pos_order])
    ax_pos.set_yticklabels([pos_label(v) for v in pos_order], fontsize=10)
    ax_pos.set_title("定位类型Pos Type时间线（UG016表4-2：单点/伪距差分/浮点/固定等）", fontsize=17, pad=12)
    ax_pos.set_ylabel("定位类型", fontsize=13)
    ax_pos.grid(alpha=.28); ax_pos.tick_params(labelsize=11)
    ax_pos.legend(fontsize=10, framealpha=.94)

    sol_order = []
    for a in analyses:
        for s in a.samples:
            if s.sol_status not in sol_order:
                sol_order.append(s.sol_status)
    sol_y = {v: i + 1 for i, v in enumerate(sol_order)}
    for i, a in enumerate(analyses):
        c = colors[i % len(colors)]
        xs = [s.t - origins[a.label] for s in a.samples]
        ys = [sol_y[s.sol_status] for s in a.samples]
        x, y = _break_gaps(xs, ys, a.gap_threshold_s)
        ax_sol.plot(x, y, color=c, lw=2.2, drawstyle="steps-post", label=a.label)
    ax_sol.set_yticks([sol_y[v] for v in sol_order])
    ax_sol.set_yticklabels([sol_label(v) for v in sol_order], fontsize=10)
    ax_sol.set_title("解算状态Sol Type时间线（UG016表4-1：SOL_COMPUTED或失败原因）", fontsize=17, pad=12)
    ax_sol.set_ylabel("解算状态", fontsize=13)
    ax_sol.set_xlabel("GPS时间（s），以本文件首个样本为0点；UNKNOWN区间为锚点回推", fontsize=14)
    ax_sol.grid(alpha=.28); ax_sol.tick_params(labelsize=11)
    ax_sol.legend(fontsize=10, framealpha=.94)

    fig.suptitle("北云UG016 GNSS卫星数量与定位/解算状态分析", fontsize=22, fontweight="bold", y=.985)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_png


def write_timeseries_csv(analyses, output: Path, x_mode="absolute"):
    origins = _origin(analyses, x_mode)
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file","relative_time_s","gps_week","gps_tow_s","time_basis","time_status","sol_status","pos_type","tracked_svs","solution_svs","solution_l1_svs","solution_multifrequency_svs","source_message"])
        for a in analyses:
            for s in a.samples:
                w.writerow([a.path.name, f"{s.t-origins[a.label]:.3f}", s.week, f"{s.tow:.3f}", s.time_basis, s.time_status, s.sol_status, s.pos_type, s.tracked, s.used, s.l1, s.multi, s.source])
    return output


def write_events_csv(analyses, output: Path):
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["event_id","file","event","gps_week","gps_tow_s","time_basis","major","detail"])
        for a in analyses:
            for e in a.events:
                w.writerow([e.event_id, a.path.name, e.label, e.week, f"{e.tow:.3f}", e.sample.time_basis if e.sample else "GPS标准时间", "是" if e.major else "否", e.detail])
    return output

# ---------------------------------------------------------------------------
# HTML报告
# ---------------------------------------------------------------------------

def _table(rows, headers):
    out = ['<div class="table-wrap"><table><thead><tr>']
    out += [f"<th>{html.escape(str(x))}</th>" for x in headers]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _status_tables(analyses):
    blocks = []
    for a in analyses:
        p = Counter(s.pos_type for s in a.samples)
        q = Counter(s.sol_status for s in a.samples)
        r = Counter(s.time_status for s in a.samples)
        blocks.append(f"<h3>{html.escape(a.path.name)}</h3>")
        blocks.append("<h4>定位类型Pos Type（表4-2）</h4>")
        blocks.append(_table([(k, n, f"{n/max(1,a.valid_count)*100:.2f}%", pos_label(k)) for k,n in p.most_common()], ["Pos Type","样本数","占比","含义/工程分组"]))
        blocks.append("<h4>解算状态Sol Type（表4-1）</h4>")
        blocks.append(_table([(k, n, f"{n/max(1,a.valid_count)*100:.2f}%", sol_label(k)) for k,n in q.most_common()], ["Sol Type","样本数","占比","含义"]))
        blocks.append("<h4>时间状态（2.1.2.1）</h4>")
        blocks.append(_table([(k,n) for k,n in r.most_common()], ["Time Status","样本数"]))
    return "".join(blocks)


def generate_html_report(analyses, report_dir: Path, x_mode="absolute", extra_sections: str = "") -> Path:
    png = plot_timeline(analyses, report_dir / "satellite_status_timeline.png", x_mode)
    write_timeseries_csv(analyses, report_dir / "timeseries.csv", x_mode)
    write_events_csv(analyses, report_dir / "key_events.csv")
    event_rows = [(e.event_id,a.path.name,e.label,format_gps_time(e.week,e.tow),"是" if e.major else "否",e.detail) for a in analyses for e in a.events]
    file_rows = []
    for a in analyses:
        st,en=a.start,a.end
        tr=[s.tracked for s in a.samples]; us=[s.used for s in a.samples]
        bad=sum(a.bad_crc_counts.values())
        file_rows.append((a.path.name,a.source,a.valid_count,a.message_counts.get(a.source,0),bad,format_gps_time(st.week,st.tow),format_gps_time(en.week,en.tow),f"{a.duration_s:.3f}",f"{a.median_period_s:.3f}" if a.median_period_s is not None else "-",f"{min(tr)}~{max(tr)}" if tr else "-",f"{min(us)}~{max(us)}" if us else "-"))
    warns = "".join(f"<li><b>{html.escape(a.path.name)}：</b>{html.escape(w)}</li>" for a in analyses for w in a.warnings)
    warn_html = f"<ul>{warns}</ul>" if warns else "<p>未发现时间轴、CRC或解析警告。</p>"
    css = "body{font-family:'Microsoft YaHei',Arial,sans-serif;max-width:1800px;margin:24px auto;padding:0 22px;background:#f7f9fb;color:#17202a}h1{font-size:30px}h2{margin-top:34px;border-bottom:2px solid #2f6fed;padding-bottom:6px}.card{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:18px;margin-bottom:20px}.table-wrap{overflow:auto;max-height:620px;border:1px solid #d9e2ec;border-radius:8px;margin:10px 0 22px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e5eef5;padding:8px 10px;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#eaf2ff}tr:nth-child(even){background:#fafcff}img{width:100%;height:auto;border:1px solid #d9e2ec;border-radius:8px}.warn{background:#fff8e6;border-left:5px solid #f0b429;padding:12px 14px}.note{font-size:13px;color:#52616b;line-height:1.65}code{background:#eef4fb;padding:2px 5px;border-radius:4px}"
    html_text = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>北云UG016 GNSS卫星数与状态分析报告</title><style>{css}</style></head><body>
<h1>北云UG016 GNSS卫星数与状态分析报告</h1>
<div class="note">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}｜文件数：{len(analyses)}｜时间轴模式：{'各文件相对起点' if x_mode=='per_file' else '绝对GPS时间对齐'}</div>
<div class="card"><h2>1. 时间线图</h2><img src="{png.name}" alt="时间线"><p class="note">图中编号对应第3节关键事件。PNG原始分辨率3600×2250像素。</p></div>
<div class="card"><h2>2. 数据与解析质量</h2>{_table(file_rows,['文件','定位源','有效时间轴样本','校验通过报文','目标报文CRC失败候选','起始时间','结束时间','跨度s','中位周期s','#SVs范围','#solnSVs范围'])}<h2>2.1 警告与限制</h2><div class="warn">{warn_html}</div></div>
<div class="card"><h2>3. 关键事件</h2>{_table(event_rows,['编号','文件','事件','GPS时间','主要事件','依据/现场值'])}</div>
<div class="card"><h2>4. 状态统计</h2>{_status_tables(analyses)}</div>
<div class="card"><h2>5. 字段口径与依据</h2><div class="note"><ul>
<li><b>卫星数量：</b>UG016 4.2.2 BESTGNSSPOS字段15 <code>#SVs</code>=跟踪卫星数，字段16 <code>#solnSVs</code>=解算卫星数，字段17/18为L1/E1/B1与多频解算卫星数。缺少BESTGNSSPOSA时回退到4.2.1 BESTPOS同序字段。</li>
<li><b>定位类型：</b>UG016表4-2。SINGLE=单点解，PSRDIFF=伪距差分，L1_FLOAT/IONOFREE_FLOAT/NARROW_FLOAT等为浮点解，L1_INT/WIDE_INT/NARROW_INT等为固定解。工程分组只用于阅读，原始英文代码保留。</li>
<li><b>解算状态：</b>UG016表4-1。SOL_COMPUTED=完全解算；INSUFFICIENT_OBS、VARIANCE等为不能完全解算的原因。它与Pos Type是两个字段，分开展示。</li>
<li><b>卫星时间：</b>UG016 2.1.2.1字段6 Time Status、字段7 GPS Week、字段8 GPSec。UNKNOWN表示尚未计算出准确GPS时间；时间轴只采用非UNKNOWN样本。报告不把GPS时间换算UTC。</li>
<li><b>CRC：</b>仅接受32-bit CRC校验通过的目标报文，失败候选不进入统计和图形。</li>
<li><b>TRACKSTATA：</b>手册4.2.26的<code>#chans</code>为硬件通道数量，通道数不是卫星数，因此不用它统计卫星颗数。</li>
<li><b>断线阈值：</b>相邻有效报文间隔大于5倍中位周期时断线；这是避免虚构连续状态的工程处理，不是手册规定。</li>
</ul></div></div>{extra_sections}</body></html>"""
    path=report_dir/"report.html"; path.write_text(html_text,encoding="utf-8"); return path


def build_report_name(paths):
    stem=paths[0].stem if len(paths)==1 else f"多文件_{paths[0].stem}_等{len(paths)}份"
    return re.sub(r'[\\/:*?"<>|\s]+','_',stem).strip('._') or 'GNSS_analysis'

def create_report_dir(root: Path, name: str):
    root.mkdir(parents=True,exist_ok=True); target=root/name
    if target.exists(): target=root/f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target.mkdir(parents=True,exist_ok=False); return target


def write_memory_note(analyses, report_dir: Path, memory_root: Path):
    memory_root.mkdir(parents=True,exist_ok=True)
    path=memory_root/f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{re.sub(r'[\\/:*?\"<>|\\s]+','_',report_dir.name)}.md"
    major=[f"- {a.path.name}｜{e.label}｜{format_gps_time(e.week,e.tow)}" for a in analyses for e in a.events if e.major]
    path.write_text(f"""# {report_dir.name} 分析记忆

- 生成时间：{datetime.now().isoformat(timespec='seconds')}
- 数据文件：
{chr(10).join(f'  - {a.path.resolve()}' for a in analyses)}
- 报告目录：{report_dir.resolve()}
- 定位源：{', '.join(sorted({a.source for a in analyses}))}
- 字段依据：UG016 4.2.2 BESTGNSSPOS字段15/16/17/18；表4-1 Sol Type；表4-2 Pos Type；2.1.2.1 Time Status/Week/Seconds。
- 解析规则：只接受CRC校验通过报文；UNKNOWN时间样本不进入时间轴；不用TRACKSTATA通道数替代卫星颗数。

## 主要事件
{chr(10).join(major) if major else '- 无主要事件。'}
""",encoding="utf-8")
    return path


def run_analysis(paths, report_root, x_mode="absolute", create_memory=True, memory_root=None):
    if not paths: raise ValueError("请至少选择一个数据文件。")
    if x_mode not in {"absolute","per_file"}: raise ValueError("时间轴模式必须是absolute或per_file。")
    ps=[Path(p) for p in paths]
    for p in ps:
        if not p.is_file(): raise FileNotFoundError(f"数据文件不存在：{p}")
    analyses=[analyze_file(p) for p in ps]
    report_dir=create_report_dir(Path(report_root),build_report_name(ps))
    report=generate_html_report(analyses,report_dir,x_mode)
    mem=None
    if create_memory:
        mem=write_memory_note(analyses,report_dir,Path(memory_root) if memory_root else Path(__file__).resolve().parent/"Memory")
    return report,analyses,mem


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def make_hash_message(name, time_status, week, tow, body):
    h=f"{name},COM1,0,50.0,{time_status},{week},{tow:.3f},00000000,0000,810"
    p=h+";"+",".join(str(x) for x in body)
    return f"#{p}*{crc32_manual(p.encode('ascii')):08X}".encode("ascii")

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"self_test.gnss"
        rows=[("UNKNOWN",100.0,"SOL_COMPUTED","NONE",0,0),("COARSE",101.0,"SOL_COMPUTED","SINGLE",8,6),("FINESTEERING",102.0,"SOL_COMPUTED","PSRDIFF",12,10),("FINESTEERING",103.0,"SOL_COMPUTED","NARROW_FLOAT",13,11),("FINESTEERING",104.0,"SOL_COMPUTED","NARROW_INT",14,12)]
        with p.open("wb") as f:
            f.write(b"binary junk")
            for i,(ts,tow,sol,pos,tr,us) in enumerate(rows):
                body=[sol,pos,31.0,121.0,10.0,0.0,"WGS84",1,1,1,'"0"',1,0,tr,us,us,max(0,us-1),0,0,0,30]
                f.write(make_hash_message("BESTGNSSPOSA",ts,2436,tow,body)+b"\r\n")
        a=analyze_file(p,"self_test")
        assert a.source=="BESTGNSSPOSA" and a.valid_count==5 and a.unknown_time_count==1 and a.extrapolated_time_count==1
        labels=[e.label for e in a.events]
        for key in ["FINESTEERING","SINGLE","PSRDIFF","NARROW_FLOAT","NARROW_INT"]:
            assert any(key in x for x in labels), key
        report,_,_=run_analysis([p],Path(td)/"report",x_mode="per_file",create_memory=False)
        for name in ["satellite_status_timeline.png","timeseries.csv","key_events.csv","report.html"]:
            assert (report.parent/name).is_file(), name
    print("SELF_TEST_PASS：CRC解析、UNKNOWN过滤、关键事件、绘图和报告导出通过。")

if __name__=="__main__": self_test()

# ---------------------------------------------------------------------------
# 扩展质量图表与诊断报告
# ---------------------------------------------------------------------------

def plot_quality_timeline(analyses, aux_data, output_png: Path, x_mode="absolute") -> Path:
    """输出室内→室外冷启动诊断图：时间状态、卫星/信号、σ、差分龄期、INS状态、位置跳变。"""
    if not analyses:
        raise ValueError("没有可绘制的数据。")
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei","SimHei","Noto Sans CJK SC","DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    origins = _origin(analyses, x_mode)
    colors = plt.get_cmap("tab10").colors
    fig,axes=plt.subplots(5,1,figsize=(22,18),dpi=170,gridspec_kw={"height_ratios":[.85,1.15,1,1,.85],"hspace":.42})
    ax_time,ax_sat,ax_sig,ax_sigma,ax_ins=axes

    for i,a in enumerate(analyses):
        c=colors[i%len(colors)]
        aux=aux_data[a.path]
        xs=[s.t-origins[a.label] for s in a.samples]
        # 时间状态：UNKNOWN=0, COARSE=1, FINESTEERING=2
        time_y={"UNKNOWN":0,"COARSE":1,"FINESTEERING":2}
        ys=[time_y.get(s.time_status.upper(),1) for s in a.samples]
        xt,yt=_break_gaps(xs,ys,a.gap_threshold_s)
        ax_time.plot(xt,yt,color=c,lw=2.2,drawstyle="steps-post",label=a.label)
    ax_time.set_yticks([0,1,2]);ax_time.set_yticklabels(["UNKNOWN｜未获得准确GPS时间","COARSE｜粗时间","FINESTEERING｜精细时间"])
    ax_time.set_title("接收机时间状态链路（UG016 2.1.2.1：室内冷启动常见 UNKNOWN→COARSE→FINESTEERING）",fontsize=16)
    ax_time.grid(alpha=.27);ax_time.legend(fontsize=10);ax_time.tick_params(labelsize=11)

    for i,a in enumerate(analyses):
        c=colors[i%len(colors)]
        xs=[s.t-origins[a.label] for s in a.samples]
        x1,y1=_break_gaps(xs,[s.tracked for s in a.samples],a.gap_threshold_s)
        x2,y2=_break_gaps(xs,[s.used for s in a.samples],a.gap_threshold_s)
        ax_sat.plot(x1,y1,color=c,lw=2.4,drawstyle="steps-post",label=f"{a.label}｜#SVs")
        ax_sat.plot(x2,y2,color=c,lw=2,ls="--",drawstyle="steps-post",label=f"{a.label}｜#solnSVs")
    ax_sat.set_title("跟踪卫星数与参与解算卫星数（BESTGNSSPOSA字段15/16；两者差异=可见但未被采用）",fontsize=16)
    ax_sat.set_ylabel("卫星数（颗）");ax_sat.grid(alpha=.27);ax_sat.legend(fontsize=9);ax_sat.tick_params(labelsize=11)

    for i,a in enumerate(analyses):
        c=colors[i%len(colors)]
        g=aux_data[a.path].gsv_epochs
        xs=[x.t-origins[a.label] for x in g]
        # 只画每颗卫星的信噪比散点；SNR=0/空不作为有效信号。
        for x,gp in zip(xs,g):
            vals=[s.snr_dbhz for s in gp.satellites if s.has_signal]
            ax_sig.scatter([x]*len(vals),vals,s=7,color=c,alpha=.35,edgecolors="none")
        # 每秒批次的信号数与高信噪比数量
        counts=[gp.with_snr for gp in g]; high=[gp.above_35dbhz for gp in g]
        x1,y1=_break_gaps(xs,counts,None);x2,y2=_break_gaps(xs,high,None)
        ax_sig.plot(x1,y1,color=c,lw=1.8,label=f"{a.label}｜GSV有SNR卫星数")
        ax_sig.plot(x2,y2,color=c,lw=1.6,ls=":",label=f"{a.label}｜SNR≥35dB-Hz")
    ax_sig.set_title("卫星信号质量：GSV逐星信噪比、GSV可见且有SNR卫星数与高信噪比卫星数（时间=批次前最近BEST时间，顺序近似）",fontsize=16)
    ax_sig.set_ylabel("SNR（dB-Hz）/ 卫星数");ax_sig.grid(alpha=.27);ax_sig.legend(fontsize=9);ax_sig.tick_params(labelsize=11)

    for i,a in enumerate(analyses):
        c=colors[i%len(colors)]
        q=summarize_quality(aux_data[a.path])
        xs=[x["t"]-origins[a.label] for x in q]
        hs=[x["h_sigma"] for x in q]
        xh,yh=_break_gaps(xs,hs,a.gap_threshold_s)
        ax_sigma.plot(xh,yh,color=c,lw=2.1,label=f"{a.label}｜水平σ=max(latσ,lonσ)")
        # 差分龄期
        ages=[x["diff_age"] if x["diff_age"] is not None else float("nan") for x in q]
        xa,ya=_break_gaps(xs,ages,a.gap_threshold_s)
        ax_sigma.plot(xa,ya,color=c,lw=1.5,ls="--",alpha=.85,label=f"{a.label}｜Diff_age")
    ax_sigma.set_ylabel("m / s");ax_sigma.set_yscale("symlog",linthresh=0.05)
    ax_sigma.set_title("接收机自估计位置质量与差分龄期（σ不是实测误差；Diff_age反映差分改正新鲜度）",fontsize=16)
    ax_sigma.grid(alpha=.27);ax_sigma.legend(fontsize=9);ax_sigma.tick_params(labelsize=11)

    ins_order=[]
    for a in analyses:
        for s in aux_data[a.path].ins:
            if s.ins_status not in ins_order:ins_order.append(s.ins_status)
    ins_y={v:i+1 for i,v in enumerate(ins_order)}
    for i,a in enumerate(analyses):
        c=colors[i%len(colors)]
        seq=aux_data[a.path].ins
        xs=[s.t-origins[a.label] for s in seq]
        ys=[ins_y[s.ins_status] for s in seq]
        x,y=_break_gaps(xs,ys,a.gap_threshold_s)
        ax_ins.plot(x,y,color=c,lw=2.1,drawstyle="steps-post",label=a.label)
    ax_ins.set_yticks([ins_y[v] for v in ins_order]);ax_ins.set_yticklabels(ins_order,fontsize=9)
    ax_ins.set_title("INS状态（UG016表4-8；INS_RTKFIXED/INS_ALIGNMENT_COMPLETE等可解释组合导航是否已可用）",fontsize=16)
    ax_ins.set_xlabel("GPS时间（s），以本文件首个样本为0点；UNKNOWN区间为锚点回推",fontsize=14)
    ax_ins.grid(alpha=.27);ax_ins.legend(fontsize=10);ax_ins.tick_params(labelsize=11)

    fig.suptitle("室内→室外冷启动GNSS问题诊断：时间/卫星/信号质量/定位σ/INS状态",fontsize=24,fontweight="bold",y=.987)
    output_png.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output_png,dpi=170,bbox_inches="tight",facecolor="white");plt.close(fig)
    return output_png


def diagnose_file(a:FileAnalysis, aux:AuxData) -> list[str]:
    """基于现有字段给出可核查的问题判断线索，不宣称唯一根因。"""
    findings=[]
    b=aux.best
    if not b:return ["未解析到BESTGNSSPOSA质量序列。"]
    valid=[s for s in b if s.time_status.upper()!="UNKNOWN"]
    if len(valid)<len(b):findings.append(f"UNKNOWN时间状态{len(b)-len(valid)}条：尚未获得准确GPS时间，可能来自室内冷启动初期或时间失效。")
    if any(s.time_status.upper()=="COARSE" for s in b):findings.append("存在COARSE时间状态：时间已粗同步但尚未到FINESTEERING。")
    if not any(s.pos_type in {"PSRDIFF","L1_FLOAT","IONOFREE_FLOAT","NARROW_FLOAT","L1_INT","WIDE_INT","NARROW_INT"} for s in b):
        findings.append("未出现伪距差分/浮点/固定解；在当前日志内GNSS链路停留在单点或无解，需检查基站数据链路、改正龄期与接收机RTK配置。")
    if aux.gsv_epochs:
        high_ratio=[g.above_35dbhz/max(1,g.with_snr) for g in aux.gsv_epochs if g.with_snr]
        if high_ratio:
            mean_ratio=sum(high_ratio)/len(high_ratio)
            findings.append(f"GSV可见且有SNR的卫星中，SNR≥35dB-Hz的批次均值占比约{mean_ratio*100:.1f}%；低占比通常提示遮挡、多径或天线/前端问题，但GSV不能唯一区分这三类原因。")
    zero_used=[s for s in b if s.tracked>0 and s.used==0]
    if zero_used:
        findings.append(f"跟踪到卫星但参与解算数为0的样本{len(zero_used)}条：接收机已看见部分信号，但观测量/几何/内部质量控制不足以形成位置解。")
    if any(s.sol_status=="VARIANCE" for s in b):findings.append("出现VARIANCE解算状态：解算方差超过限值，需结合卫星数、信号质量与接收机自估计σ继续排查。")
    if any(s.sol_status=="INSUFFICIENT_OBS" for s in b):findings.append("出现INSUFFICIENT_OBS：观测量不足，是室内弱信号/遮挡场景的直接线索。")
    if any(s.ins_status=="INS_SOLUTION_FREE" for s in aux.ins):findings.append("出现INS_SOLUTION_FREE：卫星结果较差不可用，组合导航处于自由推算/不可用状态。")
    return findings

# ---------------------------------------------------------------------------
# 报告入口：生成完整诊断报告
# ---------------------------------------------------------------------------

def run_full_analysis(paths, report_root, x_mode="absolute", create_memory=True, memory_root=None):
    if not paths:raise ValueError("请至少选择一个数据文件。")
    ps=[Path(p) for p in paths]
    for p in ps:
        if not p.is_file():raise FileNotFoundError(p)
    analyses=[analyze_file(p) for p in ps]
    outputs=[]
    for p in ps:
        a=analyze_file(p)
        aux_data={p:parse_aux(p)}
        report_dir=create_report_dir(Path(report_root),build_report_name([p]))

        quality_png=plot_quality_timeline([a],aux_data,report_dir/"coldstart_quality_diagnosis.png","per_file")
        analyses=[a]
        aux_sections=_write_aux_report(report_dir,analyses,aux_data,quality_png)
        report_path=generate_html_report([a],report_dir,"per_file",extra_sections=aux_sections)
        if create_memory:
            write_memory_note([a],report_dir,Path(memory_root) if memory_root else Path(__file__).resolve().parent/"Memory")
        outputs.append((report_dir,report_path,a,aux_data))
    return outputs
def _write_aux_report(report_dir,analyses,aux_data,quality_png):
    """为单个文件生成质量CSV、GSV CSV、AGE图，并返回追加到主报告的HTML片段。"""
    with (report_dir/"quality_timeseries.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(["file","gps_week","gps_tow_s","time_status","sol_status","pos_type","tracked","used","horizontal_sigma_m","vertical_sigma_m","diff_age_s","station_id"])
        origins=_origin(analyses,"per_file")
        for a in analyses:
            for x in summarize_quality(aux_data[a.path]):
                w.writerow([a.path.name,x["week"],f"{x['tow']:.3f}",x["time_status"],x["sol"],x["pos"],x["tracked"],x["used"],x["h_sigma"],x["v_sigma"],x["diff_age"],x["station"]])
    # 扩展CSV：GSV逐星
    with (report_dir/"gsv_satellites.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(["file","gps_week","gps_tow_s","constellation","prn","elevation_deg","azimuth_deg","snr_dbhz","has_signal"])
        for a in analyses:
            for g in aux_data[a.path].gsv_epochs:
                for s in g.satellites:
                    w.writerow([a.path.name,g.week,f"{g.tow:.3f}",s.constellation,s.prn,s.elevation_deg,s.azimuth_deg,s.snr_dbhz,"是" if s.has_signal else "否"])
    # 诊断结论
    # AGE专项输出
    age_png=plot_age_timeline(analyses,aux_data,report_dir/"age_link_audit.png","per_file")
    age_rows=age_table_rows(analyses,aux_data)
    age_html=_table(age_rows,["文件","样本数","基站ID","基站ID为空样本","Diff_age最小s","Diff_age中位s","Diff_age P95s","Diff_age最大s",">2s样本",">5s样本",">10s样本","Sol_age最小s","Sol_age最大s"])
    age_find=[]
    for a in analyses:
        for text in age_findings(a,age_summary(a,aux_data[a.path])):age_find.append((a.path.name,text))
    age_find_html=_table(age_find,["文件","AGE/差分链路结论"]) if age_find else "<p>无AGE线索。</p>"

    diag_rows=[]
    for a in analyses:
        for text in diagnose_file(a,aux_data[a.path]):diag_rows.append((a.path.name,text))
    diag_html=_table(diag_rows,["文件","诊断线索（工程判断，非唯一根因）"]) if diag_rows else "<p>无异常线索。</p>"
    css="body{font-family:'Microsoft YaHei',Arial,sans-serif;max-width:1800px;margin:24px auto;padding:0 22px;background:#f7f9fb;color:#17202a}h1{font-size:30px}h2{margin-top:34px;border-bottom:2px solid #2f6fed;padding-bottom:6px}.card{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:18px;margin-bottom:20px}.table-wrap{overflow:auto;max-height:620px;border:1px solid #d9e2ec;border-radius:8px;margin:10px 0 22px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e5eef5;padding:8px 10px;text-align:left}th{position:sticky;top:0;background:#eaf2ff}tr:nth-child(even){background:#fafcff}img{width:100%;height:auto;border:1px solid #d9e2ec;border-radius:8px}.note{font-size:13px;color:#52616b;line-height:1.65}"
    sections=f"""
<div class="card"><h2>6. 冷启动诊断时间线</h2><img src="{quality_png.name}" alt="冷启动诊断时间线"><p class="note">GSV报文自身没有GPS周/周内秒字段，图中GSV时间采用同一完整批次前最近BESTGNSSPOSA头时间，为顺序近似，已在坐标与说明中标注。</p></div>
<div class="card"><h2>7. AGE / 差分链路专项审计</h2><img src="{age_png.name}" alt="AGE与差分链路审计"><p class="note">Diff_age=UG016 4.2.2字段13，单位s；Sol_age=字段14；基站ID=字段12。2s/5s只是工程审计提示线，不是手册限值。</p>{age_html}<h3>AGE/差分链路结论</h3>{age_find_html}</div>
<div class="card"><h2>8. 诊断线索</h2>{diag_html}</div>
<div class="card"><h2>9. 行业常见原因与现有字段覆盖</h2><div class="note"><ul>
<li><b>信号可见性/遮挡：</b>GSV视野内卫星数、仰角、方位角、SNR；BESTGNSSPOSA #SVs/#solnSVs。</li>
<li><b>多径/信号质量退化：</b>GSV SNR分布、SNR≥35dB-Hz占比、#SVs与#solnSVs差异；现有字段不能唯一区分多径和遮挡。</li>
<li><b>卫星几何：</b>当前日志未录制GSA/GST/DOP类报文，无法量化PDOP/HDOP/位置残差。</li>
<li><b>时间同步：</b>标准头Time Status UNKNOWN/COARSE/FINESTEERING；室内冷启动首先看UNKNOWN是否长期持续。</li>
<li><b>差分链路：</b>Diff_age、基站ID、定位类型；无PSRDIFF/浮点/固定且Diff_age异常，应先查改正数据链路。</li>
<li><b>组合导航：</b>INSPVAXA INS状态与位置类型；INS_INACTIVE/INS_SOLUTION_FREE说明INS未形成可用辅助。</li>
<li><b>接收机自估计质量：</b>BESTGNSSPOSA lat/lon/hgt σ；这是接收机估计精度，不是实测误差。</li>
</ul></div></div>"""
    return sections




# ---------------------------------------------------------------------------
# Diff_age / Sol_age 专项审计与绘图
# ---------------------------------------------------------------------------

def age_summary(a: FileAnalysis, aux: AuxData) -> dict:
    """统计差分龄期、解算龄期、基站ID是否变化或丢失。阈值是审计阈值，非手册规定。"""
    rows=[]
    prev=None
    for s in aux.best:
        row=dict(
            t=s.t,week=s.week,tow=s.tow,time_status=s.time_status,
            sol=s.sol_status,pos=s.pos_type,diff_age=s.diff_age,
            sol_age=s.sol_age,station=s.station_id,
            age_available=s.station_id != "" and s.diff_age is not None,
        )
        rows.append(row)
    diff=[x["diff_age"] for x in rows if x["diff_age"] is not None]
    sol=[x["sol_age"] for x in rows if x["sol_age"] is not None]
    stations=sorted({x["station"] for x in rows if x["station"]})
    # 阈值用于审计提示，不作为手册限值。
    age_gt_2=[x for x in rows if x["diff_age"] is not None and x["diff_age"]>2.0]
    age_gt_5=[x for x in rows if x["diff_age"] is not None and x["diff_age"]>5.0]
    age_gt_10=[x for x in rows if x["diff_age"] is not None and x["diff_age"]>10.0]
    no_station=[x for x in rows if not x["station"]]
    # station连续段
    segments=[]
    for x in rows:
        if not segments or segments[-1][0] != x["station"]:
            segments.append([x["station"],x["t"],x["t"],1])
        else:
            segments[-1][2]=x["t"];segments[-1][3]+=1
    return dict(
        rows=rows,count=len(rows),diff_count=len(diff),sol_count=len(sol),
        diff_min=min(diff) if diff else None,diff_max=max(diff) if diff else None,
        diff_median=statistics.median(diff) if diff else None,
        diff_p95=sorted(diff)[int(0.95*(len(diff)-1))] if diff else None,
        sol_min=min(sol) if sol else None,sol_max=max(sol) if sol else None,
        sol_median=statistics.median(sol) if sol else None,
        age_gt_2=len(age_gt_2),age_gt_5=len(age_gt_5),age_gt_10=len(age_gt_10),
        age_gt_2_first=age_gt_2[0] if age_gt_2 else None,
        age_gt_5_first=age_gt_5[0] if age_gt_5 else None,
        stations=stations,no_station_count=len(no_station),
        station_segments=segments,
    )


def age_findings(a: FileAnalysis, summary: dict) -> list[str]:
    out=[]
    if summary["diff_count"]==0 or all(x["diff_age"] in (None,0.0) for x in summary["rows"]):
        out.append("BESTGNSSPOSA中的Diff_age全部为0或缺失，且无有效基站ID：当前日志不能证明RTK差分改正曾被接收。")
    if summary["stations"]:
        out.append(f"基站ID始终出现为{','.join(summary['stations'])}，Diff_age有非零值，说明接收机记录到差分改正龄期；但这只能证明有差分数据龄期字段，不能证明RTK模糊度可用。")
    else:
        out.append("基站ID为空：当前日志未体现有效差分基准站。")
    if summary["age_gt_2"]:
        first=summary["age_gt_2_first"]
        out.append(f"Diff_age>2s的样本{summary['age_gt_2']}条；首次在GPS {first['week']}周 {first['tow']:.3f}s，当时Pos Type={first['pos']}，最大Diff_age={summary['diff_max']:.3f}s。")
    if summary["age_gt_5"]:
        first=summary["age_gt_5_first"]
        out.append(f"Diff_age>5s的样本{summary['age_gt_5']}条；首次在GPS {first['week']}周 {first['tow']:.3f}s，需要检查基准站数据链路或输出间隔。")
    if summary["diff_max"] is not None and summary["diff_max"] <= 2.0:
        out.append("Diff_age最大值未超过2s：从龄期看没有长时间差分改正失效。")
    if summary["no_station_count"]:
        out.append(f"基站ID为空的样本{summary['no_station_count']}条，通常对应单点/无解状态，不能作为RTK可用。")
    return out


def plot_age_timeline(analyses, aux_data, output_png: Path, x_mode="absolute") -> Path:
    plt.rcParams["font.sans-serif"]=["Microsoft YaHei","SimHei","Noto Sans CJK SC","DejaVu Sans"];plt.rcParams["axes.unicode_minus"]=False
    origins=_origin(analyses,x_mode);colors=plt.get_cmap("tab10").colors
    fig,axes=plt.subplots(3,1,figsize=(20,12),dpi=180,gridspec_kw={"height_ratios":[1.2,.8,.8],"hspace":.38})
    ax_age,ax_station,ax_sol=axes
    for i,a in enumerate(analyses):
        c=colors[i%len(colors)];rows=age_summary(a,aux_data[a.path])["rows"]
        xs=[x["t"]-origins[a.label] for x in rows]
        ys=[x["diff_age"] if x["diff_age"] is not None else float("nan") for x in rows]
        x,y=_break_gaps(xs,ys,a.gap_threshold_s)
        ax_age.plot(x,y,color=c,lw=2.0,drawstyle="steps-post",label=a.label)
        ax_age.axhline(2,color="orange",lw=1.2,ls="--",alpha=.75)
        ax_age.axhline(5,color="red",lw=1.2,ls="--",alpha=.75)
        # station presence: 0 empty, 1 station
        st=[0 if not x["station"] else 1 for x in rows]
        xs2,ys2=_break_gaps(xs,st,a.gap_threshold_s)
        ax_station.plot(xs2,ys2,color=c,lw=2.0,drawstyle="steps-post",label=a.label)
        ys3=[x["sol_age"] if x["sol_age"] is not None else float("nan") for x in rows]
        xs3,ys3=_break_gaps(xs,ys3,a.gap_threshold_s)
        ax_sol.plot(xs3,ys3,color=c,lw=1.8,drawstyle="steps-post",label=a.label)
    ax_age.set_title("Diff_age差分龄期时间线（字段13；2s/5s为审计提示线，非手册限值）",fontsize=17)
    ax_age.set_ylabel("Diff_age（s）");ax_age.grid(alpha=.27);ax_age.legend(fontsize=10);ax_age.tick_params(labelsize=11)
    ax_station.set_yticks([0,1]);ax_station.set_yticklabels(["基站ID为空","基站ID存在"])
    ax_station.set_title("基站ID存在性（字段12；为空不能作为RTK可用）",fontsize=17);ax_station.grid(alpha=.27);ax_station.legend(fontsize=10);ax_station.tick_params(labelsize=11)
    ax_sol.set_title("Sol_age解算延迟时间线（字段14）",fontsize=17);ax_sol.set_ylabel("Sol_age（s）")
    ax_sol.set_xlabel("相对时间（s）",fontsize=14);ax_sol.grid(alpha=.27);ax_sol.legend(fontsize=10);ax_sol.tick_params(labelsize=11)
    fig.suptitle("差分改正龄期与基站链路审计",fontsize=23,fontweight="bold",y=.985)
    output_png.parent.mkdir(parents=True,exist_ok=True);fig.savefig(output_png,dpi=180,bbox_inches="tight",facecolor="white");plt.close(fig)
    return output_png


def age_table_rows(analyses, aux_data):
    rows=[]
    for a in analyses:
        s=age_summary(a,aux_data[a.path])
        rows.append((a.path.name,s["count"],s["stations"],s["no_station_count"],
                     f"{s['diff_min']:.3f}" if s["diff_min"] is not None else "-",
                     f"{s['diff_median']:.3f}" if s["diff_median"] is not None else "-",
                     f"{s['diff_p95']:.3f}" if s["diff_p95"] is not None else "-",
                     f"{s['diff_max']:.3f}" if s["diff_max"] is not None else "-",
                     s["age_gt_2"],s["age_gt_5"],s["age_gt_10"],
                     f"{s['sol_min']:.3f}" if s["sol_min"] is not None else "-",
                     f"{s['sol_max']:.3f}" if s["sol_max"] is not None else "-"))
    return rows

