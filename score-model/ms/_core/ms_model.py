# -*- coding: utf-8 -*-
"""MS 容器。"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field, replace as dc_replace

import ms_semantics as ms


# ── 常量 ──────────────────────────────────────────────────────
KEY_MIN, KEY_MAX = 21, 108          # A0..C8
EXCITATION_TYPES = ("impulse", "sustained")
RELEASE_STATES = ("given", "sustaining", "NOT_PROVIDED")
DYNAMICS_MIN, DYNAMICS_MAX = 1, 100000
DYNAMICS_NEUTRAL = 1000             # = MIDI velocity 64
DYNAMICS_SCALES = ("relative_permille", "velocity_steps", "continuous", "fixed_levels")
DYNAMICS_SRCS = ("measured", "midi_inverted", "notated_inferred", "composed")
PEDAL_KINDS = ("sustain", "sostenuto", "una_corda",   # 制音类
               "tuning", "swell", "hihat",            # 调音/表情/踩镲
               "sordino")                             # 弱音器装上/取下（弓弦、管乐）
# 注：wah / 移调 属**连续演奏动作**，不是踏板状态，不进本表（见 KNOWN_LIMITS）。
PEDAL_SCOPES = ("mechanical", "explicit")
CONSTRAINT_MODES = ("single_piano", "n_pianos", "unlimited")
CHANNEL_MODES = ("per_instance", "per_section")   # MIDI 通道粒度（见 PLAYBACK §1.1）
DEPTH_MIN, DEPTH_MAX = 0, 1000

ERR_PITCH_RANGE = "UNSUPPORTED_PITCH_RANGE"


def key_number(semitone: int) -> int:
    """键号由半音派生（不存储）。C# 与 Db 得到同一键号。"""
    return int(semitone)


@dataclass(frozen=True)
class Pitch:
    """音高双轨：拼写（step/alter/octave）+ 半音。键号由半音派生，不另存。"""
    step: str
    alter: int
    octave: int
    semitone: int

    def consistent(self) -> bool:
        base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        if self.step not in base:
            return False
        if not (-2 <= self.alter <= 2):
            return False
        return base[self.step] + self.alter + (self.octave + 1) * 12 == self.semitone

    def key(self) -> int:
        return key_number(self.semitone)


@dataclass(frozen=True)
class Dynamics:
    """力度：无量纲乘性系数（缺失与中性不同，见 ms_semantics）。"""
    state: str                       # ms.VALUE | ms.NOT_PROVIDED
    permille: int | None = None
    scale: str | None = None
    calibration_ref: str | None = None
    src: str | None = None


@dataclass(frozen=True)
class PedalSegment:
    """踏板控制事件：**和音符一样带 id 与乐器**，按时间覆盖绑定音符。

    它不是全局区间表：`instrument_id` 说明是哪台乐器的踏板；
    作用于哪些音由时间决定（按压期间仍在响的音 + 按压时刻起的音）。
    """
    instrument_id: int
    kind: str
    start_us: int
    end_us: int | None
    depth_permille: int
    scope: str = "mechanical"
    targets: tuple | None = None     # 仅 explicit：("global",) 或 note_id 元组
    id: str | None = None            # 控制事件 id（`D`+8 位）；None = 旧 7 列写法


@dataclass(frozen=True)
class Event:
    id: str
    instrument_id: int
    onset_us: int
    pitch: Pitch
    excitation_type: str = "impulse"
    release_us: int | None = None
    release_state: str = "given"
    dynamics: Dynamics = dc_field(default_factory=lambda: Dynamics(ms.NOT_PROVIDED))
    is_grace: bool = False
    # 止音（release）的**方式**与**缓冲**：不是"到点就没了"。
    #   off_kind  None = 按该乐器的机制查默认（见 ms_instruments.OFF_DEFAULTS）
    #   off_ramp_us 止音过程长度（µs）：从 release_us 起按这个长度衰减到无声
    off_kind: str | None = None
    off_ramp_us: int = 0

    def key(self) -> int:
        return self.pitch.key()


@dataclass
class Instrument:
    """本曲使用的乐器实例（"几号乐器/几号人"）。能力查总登记表，不写进文件。"""
    id: str                      # P1 / P2 …（实例号，文件内唯一）
    type: str                    # 类型码（GM 名称，如 acoustic_grand_piano / violin）
    subtype: str | None = None   # 子类型码（如 steinway_d / yamaha_c7），可空
    section: str | None = None   # 声部/组（如 choir_s / choir_a / strings_1）；per_section 按它合并
    constraints: dict | None = None  # 收束结构覆盖（可空；默认取机制级）


@dataclass
class CurvePoint:
    """控制曲线的一个点：**起点值 / 转折点**。

    MS 只记点；点与点之间怎么插值由渲染层决定（P1：计算只吃数值）。
      · ramp=0 阶跃：从此刻起直接取 value（起点或转折）
      · ramp=1 渐进：从上一个点线性渐变到本点的 value（渐强/渐弱）

    param 支持：dynamics（0..1000‰）、brightness（0..1000）、pitch_cents（±2400）。
    """
    instrument_id: int
    param: str
    time_us: int
    value: int
    ramp: int = 0            # 0=阶跃（起点） 1=渐进


@dataclass
class TurnPoint:
    """演奏转折：一个事件**音头**的方式，挂在事件上。

    转折既是可演奏性的复位（同键再击 / 换弓 / 换气），也是**声音事实**：
    再击有槌/指的音头，换弓有弓毛摩擦，换气有气口。因此进 MS 结构。

      · retrigger   同键再击（上一音与本音同音高）
      · bow_change  换弓（弓弦专属）
      · breath      换气/吐音（吹奏、人声）
      · restrike    重复拨弦（拨弦）
      · mallet      换槌/换手（击体）

    strength：音头强度 0..1000（1000=正常重音，0=几乎无痕的连奏）。
    """
    event_id: str
    kind: str
    strength: int = 1000
    seg_index: int | None = None   # 可选：指向该音的某一个段（段间转折）


@dataclass
class VoiceSegment:
    """字的发音段（声母/介音/主音/韵尾），段级事实。

    同一 `structure_id` 的段组成一个完整汉字（最大闭合单元）。
    段级 `tone` 是**发声声调**，可以与字级词典声调不同（V-tone-split）。
    `turn=1` 表示该段前重新起音（段间转折）。
    """
    structure_id: str      # 绑定关系 ID（字典里的组合编号）
    index: int             # 段内顺序
    kind: str              # initial | medial | nucleus | coda
    text: str              # 段本身：x / ing / ch / ang
    tone: int              # 段级声调
    onset_us: int = 0
    release_us: int = 0
    turn: int = 0          # 转折规则（交收束层解释）
    event_id: str = ""     # 属于哪个音
    binding_id: str = ""   # 与 structure_id 同义，便于读写
    lang: str | None = None  # zh/en/fr/ja/ru


@dataclass
class MSDocument:
    """MS 容器：事件表 + 踏板轨 + 约束档 + 缺口记录。不含网格/速度/记谱语境/呈现信息。"""
    piano_count: int = 1
    constraint_mode: str = "single_piano"
    events: list = dc_field(default_factory=list)
    pedals: list = dc_field(default_factory=list)      # list[PedalSegment]
    gaps: list = dc_field(default_factory=list)        # 缺口/未提供记录（自由结构）
    retired_ids: list = dc_field(default_factory=list)  # 作废 id 簿记
    channels: str = "per_instance"                     # per_instance | per_section（影响 MIDI 导出）
    instruments: list = dc_field(default_factory=list)  # list[Instrument]；空 = 隐式单钢琴
    curves: list = dc_field(default_factory=list)      # list[CurvePoint]：起点/转折/渐进
    turns: list = dc_field(default_factory=list)       # list[TurnPoint]：演奏转折（音头）
    # 结尾**显式**留白（微秒）：0 = 严格对齐到内容结束；>0 = 作者声明的空白
    trailing_silence_us: int = 0
    segments: list = dc_field(default_factory=list)  # list[VoiceSegment]（写在事件流里）


def content_end_us(doc) -> int:
    """内容结尾：最后一个音的释放（无释放取起点）。"""
    return max([(e.release_us if e.release_us is not None else e.onset_us)
                for e in doc.events] + [0])


def pedal_applies(pedal, event) -> bool:
    """踏板是否作用于这个音：**先看乐器**，再看显式 `targets`。

    踏板是 per-instrument 的持续控制（`PedalSegment.instrument_id`），
    按乐器分轨。
    `targets` 里写 `global` 才表示该乐器内所有音（默认），否则只作用于列出的音。
    """
    if getattr(pedal, "instrument_id", None) != getattr(event, "instrument_id", None):
        return False
    targets = getattr(pedal, "targets", None) or ()
    if not targets:
        return True
    return ("global" in targets) or (getattr(event, "id", None) in targets)


def instrument_of(doc, instrument_id: int):
    """按 **id**（`P8` → 8）取本曲声明的乐器实例；没有就返回 None。

    乐器号是**身份**，不是数组下标：声明了 P1/P8 时，8 号乐器就是 P8，
    不能因为它是第二项就取到 P1。
    """
    for inst in getattr(doc, "instruments", []) or []:
        pid = str(getattr(inst, "id", ""))
        if pid == f"P{instrument_id}" or pid == str(instrument_id):
            return inst
    return None


def declared_instrument_ids(doc) -> set:
    """本曲声明过的乐器 id 集合（无 instruments 块时按 piano_count 隐含 1..n）。"""
    insts = getattr(doc, "instruments", None)
    if insts:
        out = set()
        for inst in insts:
            pid = str(getattr(inst, "id", ""))
            if pid.startswith("P") and pid[1:].isdigit():
                out.add(int(pid[1:]))
            elif pid.isdigit():
                out.add(int(pid))
        return out
    return set(range(1, int(getattr(doc, "piano_count", 1) or 1) + 1))


PEDAL_REPRESS_TOL_US = 50_000     # 换踩容差：抬脚后 50ms 内再踩，声音不断


def assign_pedal_ids(pedals) -> list:
    """给没有 id 的踏板补 `D`+8 位；**已有 id 的一律不动**（E4：id 稳定）。"""
    used = {getattr(p, "id", None) for p in pedals if getattr(p, "id", None)}
    out, n = [], 1
    for p in pedals:
        if getattr(p, "id", None):
            out.append(p)
            continue
        while f"D{n:08d}" in used:
            n += 1
        pid = f"D{n:08d}"
        used.add(pid)
        out.append(dc_replace(p, id=pid))
    return out


def sustain_end_us(doc, event) -> int:
    """这个音被**本乐器**的延音踏板按到什么时候。

    不是"只看音头所在的那一段"：踏板在音还响着的时候**换踩**（中间一般有几十毫秒
    抬脚），新的一段会接着按住它——所以按时间链式接续，容差 `PEDAL_REPRESS_TOL_US`。
    """
    end = event.release_us if event.release_us is not None else event.onset_us
    segs = sorted((p for p in doc.pedals
                   if p.kind == "sustain" and pedal_applies(p, event)),
                  key=lambda p: p.start_us)
    changed = True
    while changed:
        changed = False
        for p in segs:
            if p.end_us is None or p.end_us <= end:
                continue
            if p.start_us <= end + PEDAL_REPRESS_TOL_US:
                end = p.end_us
                changed = True
    return end


def sounding_end_us(doc) -> int:
    """发声结尾：把 sustain / sostenuto 的延长算进去后的实际有声结尾。

    踏板本身不发声——只有当它踩在**同一乐器的**音上才延长该音。因此：
      · 踏板超出所有音 → 不会产生额外声音（这正是"尾段静音"的根源）
      · 该函数就是"内容真正有多长"的判据
    """
    end = 0
    sosts = [p for p in doc.pedals if p.kind == "sostenuto"]
    for e in doc.events:
        if getattr(e, "release_state", "given") == "sustaining":
            continue          # 未释放：由消费方决定，不计入确定结尾
        e_end = sustain_end_us(doc, e)
        for p in sosts:
            if pedal_applies(p, e) and p.targets and p.start_us <= e.onset_us:
                e_end = max(e_end, p.end_us if p.end_us is not None else e.onset_us)
        end = max(end, e_end)
    return end


def total_end_us(doc) -> int:
    """总时长：发声结尾 + **显式声明**的结尾留白。"""
    return sounding_end_us(doc) + max(0, getattr(doc, "trailing_silence_us", 0) or 0)
