# -*- coding: utf-8 -*-
"""ScoreV02 语义模型（分析层的数据结构）。"""
from __future__ import annotations

from dataclasses import dataclass, field

STEP_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# 记谱拼写 → 半音；黑键两种拼写都合法，语义靠 alter 区分
FIFTHS_TO_MAJOR = {0: ("C", 0)}  # 仅示例锚；实际用 step/alter 直接算


@dataclass(frozen=True)
class PitchSpell:
    """记谱拼写与计算音高双轨（契约 §3.4）。"""
    step: str          # C D E F G A B
    alter: int         # -2..2（bb/b/自然/#/##）
    octave: int

    @property
    def semitone(self) -> int:
        return 12 * (self.octave + 1) + STEP_BASE[self.step] + self.alter

    @property
    def spelling(self) -> str:
        acc = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}[self.alter]
        return f"{self.step}{acc}{self.octave}"

    def consistent(self) -> bool:
        """拼写与半音一致（契约：可校验）。"""
        return self.semitone == 12 * (self.octave + 1) + STEP_BASE[self.step] + self.alter


@dataclass
class AccidentalContext:
    """调号 + 小节内临时记号作用范围（契约 §3.4）。

    规则：临时记号在本小节、本声部、同音名同八度内持续生效（标准记谱惯例的
    机器可读近似；换小节即失效）。导入时不得只算半音丢掉本上下文。
    """
    key_fifths: int = 0          # 调号升降数（-7..7）
    _active: dict = field(default_factory=dict)  # (voice, step, octave) -> alter

    def new_measure(self) -> None:
        self._active.clear()

    def apply_notated(self, spell: PitchSpell, voice: str, has_accidental: bool) -> PitchSpell:
        """返回考虑语境后的拼写；has_accidental=True 表示谱面有临时记号。"""
        if has_accidental:
            self._active[(voice, spell.step, spell.octave)] = spell.alter
            return spell
        key = (voice, spell.step, spell.octave)
        if key in self._active:
            return PitchSpell(spell.step, self._active[key], spell.octave)
        return spell


# ── L1 记谱事件层 ──
@dataclass
class NotationEvent:
    id: str
    onset: int                 # 权威：网格单位
    duration: int              # 权威：网格单位
    voice: str
    staff: str
    measure: int

    @property
    def offset(self) -> int:
        return self.onset + self.duration


@dataclass
class NoteEvent(NotationEvent):
    pitch: PitchSpell = None  # type: ignore[assignment]
    is_grace: bool = False
    grace_order: int | None = None      # 同一主体音前的装饰音序
    principal_id: str | None = None     # 主体音引用（grace 专用）
    tie_start_ids: list = field(default_factory=list)   # TieGroup.id
    tie_stop_ids: list = field(default_factory=list)
    articulation_ids: list = field(default_factory=list)
    # ── s02-1.1 承载槽（M-6.1，管理者 2026-10-19 裁定）──
    # 力度：与 MS 同单位（1000‰ ↔ MIDI 64）。None = 未提供，**不得**用 1000 冒充。
    dynamics_permille: int | None = None
    # 释放：三态。given=给了时值；sustaining=按住不放（消费方决定怎么结束）；
    # NOT_PROVIDED=未提供。三者不可互代。
    release_state: str = "given"
    instrument_id: int = 1          # 对应 MS 的乐器实例号（1 基）


@dataclass
class RestEvent(NotationEvent):
    """休止是独立对象，不是空音符（契约 §3.1）。"""


@dataclass
class TieGroup:
    """记谱 tie 关系：成员有序，可跨小节（契约 §3.2）。

    演奏层的持续发声事件是 L3 的事，不在本对象内合并成员。
    """
    id: str
    member_ids: list           # NoteEvent.id，记谱顺序
    voice: str


@dataclass
class Tuplet:
    """连音组：比例 + 成员 + 嵌套（契约 §3.5）。ratio=(实际音数, 占本位数)"""
    id: str
    ratio: tuple               # (3, 2) 表示三连音
    member_ids: list
    parent_id: str | None = None


@dataclass
class ArticulationMark:
    id: str
    kind: str                  # staccato / accent / tenuto ...
    target_ids: list           # 作用对象（契约 §3.6）


# ── 演奏层（L3）：动作 / 连续参数 / 发声段（2026-10-24 新增）──
@dataclass
class ActionMark:
    """逐音动作：对应 MS 的 `turns`。

    kind 与 MS 同名同值（bow_up/pizz/tremolo/mute_harmon/…），
    strength 0..1000；target = 挂在哪个音上。
    """
    id: str
    kind: str
    target_id: str
    strength: int = 1000


@dataclass
class CurveLane:
    """逐乐器连续参数：对应 MS 的 `curves`（dynamics/brightness/pitch_cents/vibrato/bow_position）。"""
    instrument_id: int
    param: str
    time_us: int
    value: int
    ramp: int = 0


@dataclass
class VoiceSegmentV02:
    """人声发声段：对应 MS 事件流里的 `vocal` 行（一个声母或一个韵母，自带时间）。"""
    event_id: str
    index: int
    kind: str                  # initial / medial / nucleus / coda
    text: str
    binding_id: str
    tone: int = 0
    turn: int = 0
    lang: str | None = None
    onset_us: int = 0
    end_us: int = 0


# ── 踏板：记号层（L1）──
@dataclass
class PedalMark:
    """踏板记号：类型 + 精确记谱时间 + 作用范围（契约 §3.8）。

    pedal_type: sustain | sostenuto | una_corda
    action_notated: start | change | stop（记号语义，不是执行解释）
    """
    id: str
    pedal_type: str
    action_notated: str
    onset: int
    measure: int
    target_scope: list | None = None   # sostenuto：触发时刻被保持的音符 id 集
    source: str = "composed"
    # ── s02-1.1 承载槽（M-6.1）──
    # 深度：0..1000‰。None = 只是开关记号（无深度信息），**不得**用 1000 冒充。
    # 保留 action_notated（记谱动作）与深度（执行参数）分层，二者不互代。
    depth_permille: int | None = None


# ── L3 执行层接口位（定义关系，计算暂缓 —— 契约 §4）──
@dataclass
class PedalControlEvent:
    """踏板控制轨迹事件。时间不混：time_kind 决定单位。"""
    pedal_type: str
    action: str                # press | hold | release
    time_kind: str             # "grid" | "sec" —— 记谱时间与实际时间不混
    time: int | float
    control_value: float | None = None   # 输入值（开关/深度），≠机构响应≠声音
    source: str = "interpreted"
    target_scope: list | None = None


@dataclass
class ScoreV02:
    """作品整体（L1 集合 + 上下文）。"""
    title: str = ""
    grid_units_per_quarter: int = 4   # 权威时间网格；含三连音时用 12 等
    key_fifths: int = 0
    time_beats: int = 4
    time_beat_type: int = 4
    notes: list = field(default_factory=list)
    rests: list = field(default_factory=list)
    tie_groups: list = field(default_factory=list)
    tuplets: list = field(default_factory=list)
    articulations: list = field(default_factory=list)
    pedal_marks: list = field(default_factory=list)
    words: list = field(default_factory=list)
    # s02-1.1 起：出现承载槽（力度/释放/踏板深度）。1.0 文件无此字段，读取按 1.0 处理。
    instruments: list = field(default_factory=list)   # [{id,type,subtype,section}]
    # s02-2 起：演奏层（动作 / 连续参数 / 发声段）——从 MS 的 turns/curves/vocal 投影
    actions: list = field(default_factory=list)       # list[ActionMark]
    curves: list = field(default_factory=list)        # list[CurveLane]
    segments: list = field(default_factory=list)      # list[VoiceSegmentV02]
    schema_version: str = "s02-2"

    # ── 派生（float 仅派生，契约 §2）──
    def beats(self, grid_units: int) -> float:
        return grid_units / self.grid_units_per_quarter

    def simultaneous(self, t: int) -> list:
        return [e for e in self.all_events() if e.onset == t]

    def all_events(self) -> list:
        return list(self.notes) + list(self.rests)

    def tie_of(self, note_id: str) -> TieGroup | None:
        for g in self.tie_groups:
            if note_id in g.member_ids:
                return g
        return None

    def sustained_spans(self) -> list:
        """L2 派生：tie 组合成的持续发声（不改写 L1 成员）。

        返回 [(first_note_id, voice, start, end)]，end 取末成员 offset。
        """
        spans = []
        for g in self.tie_groups:
            members = [n for nid in g.member_ids
                       for n in self.notes if n.id == nid]
            if not members:
                continue
            first, last = members[0], members[-1]
            spans.append((first.id, g.voice, first.onset, last.offset))
        return spans

    # ── 校验（契约验收的机器面）──
    def validate(self) -> list:
        errs = []
        ids = {e.id for e in self.all_events()}
        for n in self.notes:
            if getattr(n, "instrument_id", 1) < 1:
                errs.append(f"note {n.id}: instrument_id 必须 >= 1")

        # s02-2：演奏层引用必须落在真实事件上
        for a in self.actions:
            if a.target_id not in ids:
                errs.append(f"action {a.id}: 目标 {a.target_id} 不存在")
            if not (0 <= a.strength <= 1000):
                errs.append(f"action {a.id}: strength 越界 {a.strength}")
        for c in self.curves:
            if c.instrument_id < 1:
                errs.append(f"curve: instrument_id 必须 >= 1（{c.instrument_id}）")
            if not (0 <= c.ramp <= 1):
                errs.append(f"curve: ramp 只能是 0/1（{c.ramp}）")
        for s in self.segments:
            if s.event_id not in ids:
                errs.append(f"segment: 事件 {s.event_id} 不存在")
            if s.kind not in ("initial", "medial", "nucleus", "coda"):
                errs.append(f"segment: 未知段类型 {s.kind}")
            if s.end_us and s.onset_us and s.end_us <= s.onset_us:
                errs.append(f"segment: 段时长非正（{s.event_id}#{s.index}）")

        for g in self.tie_groups:
            if not g.member_ids:
                errs.append(f"tie {g.id}: 空成员")
            for mid in g.member_ids:
                if mid not in ids:
                    errs.append(f"tie {g.id}: 成员 {mid} 不存在")
        for t in self.tuplets:
            if t.parent_id and t.parent_id not in {x.id for x in self.tuplets}:
                errs.append(f"tuplet {t.id}: 嵌套父 {t.parent_id} 不存在")
        for a in self.articulations:
            for tid in a.target_ids:
                if tid not in ids:
                    errs.append(f"articulation {a.id}: 目标 {tid} 不存在")
        for p in self.pedal_marks:
            if p.pedal_type not in ("sustain", "sostenuto", "una_corda",
                                    "tuning", "swell", "hihat", "sordino"):
                errs.append(f"pedal {p.id}: 未知类型 {p.pedal_type}")
            if p.pedal_type == "sostenuto" and p.action_notated == "start" \
                    and p.target_scope is None:
                errs.append(f"pedal {p.id}: sostenuto start 必须带 target_scope（保持哪些音符）")
            # s02-1.1 承载槽：深度必须 0..1000（None = 无深度信息，合法）
            d = getattr(p, "depth_permille", None)
            if d is not None:
                if not isinstance(d, int) or isinstance(d, bool):
                    errs.append(f"pedal {p.id}: depth_permille 必须是整数（当前 {d!r}）")
                elif not (0 <= d <= 1000):
                    errs.append(f"pedal {p.id}: depth_permille 越界 {d}（应在 0..1000）")
        for n in self.notes:
            if n.pitch is not None and not n.pitch.consistent():
                errs.append(f"note {n.id}: 拼写与半音不一致")
            # s02-1.1 承载槽：力度 1..100000（None = 未提供，合法且不等于 1000）
            d = getattr(n, "dynamics_permille", None)
            if d is not None:
                if not isinstance(d, int) or isinstance(d, bool):
                    errs.append(f"note {n.id}: dynamics_permille 必须是整数（当前 {d!r}）")
                elif not (1 <= d <= 100000):
                    errs.append(f"note {n.id}: dynamics_permille 越界 {d}（应在 1..100000）")
            # 释放三态：只许三值，不许自造
            rs = getattr(n, "release_state", "given")
            if rs not in ("given", "sustaining", "NOT_PROVIDED"):
                errs.append(f"note {n.id}: release_state 非法 {rs!r}（只许 given/sustaining/NOT_PROVIDED）")
        # 精确时间：网格为整数
        for e in self.all_events():
            if not isinstance(e.onset, int) or not isinstance(e.duration, int):
                errs.append(f"event {e.id}: 时间权威必须是整数网格")
        # ── G2 构造侧不变量（构造/恢复路径必须能拒绝的错误）──
        for e in self.all_events():
            # grace 音符记谱无 duration → 零时值合法（G6 观察项收口：豁免仅限 is_grace）
            if e.duration <= 0 and not getattr(e, "is_grace", False):
                errs.append(f"event {e.id}: 时值必须为正")
            if e.onset < 0:
                errs.append(f"event {e.id}: 起点不能为负")
        by_voice = {}
        for e in self.all_events():
            by_voice.setdefault(e.voice, []).append(e)
        for v, evs in by_voice.items():
            evs = sorted(evs, key=lambda x: (x.onset, x.id))
            for a, b in zip(evs, evs[1:]):
                # 同起音=和弦（合法）；tie 首尾相接（offset==onset）合法
                if b.onset != a.onset and b.onset < a.offset:
                    errs.append(
                        f"voice {v}: 同声部时间重叠 {a.id}@{a.onset}+{a.duration}"
                        f" 与 {b.id}@{b.onset}")
        for g in self.tie_groups:
            mem = [n for nid in g.member_ids for n in self.notes if n.id == nid]
            for x, y in zip(mem, mem[1:]):
                if x.pitch is not None and y.pitch is not None \
                        and x.pitch.semitone != y.pitch.semitone:
                    errs.append(f"tie {g.id}: 成员音高不一致 {x.id}->{y.id}")
                if x.offset != y.onset:
                    errs.append(f"tie {g.id}: 成员时间断裂 {x.id}@{x.offset}->{y.id}@{y.onset}")
                if x.voice != y.voice:
                    errs.append(f"tie {g.id}: 成员声部不一致 {x.id}/{y.id}")
        return errs


def grid_for_tuplets(base: int = 4, tuplet_nums: tuple = (3, 5, 7)) -> int:
    """按需放大网格使常见连音组精确可分（如 4→12 可表三连音）。"""
    from math import gcd
    u = base
    for n in tuplet_nums:
        u = u * n // gcd(u, n)
    return u
