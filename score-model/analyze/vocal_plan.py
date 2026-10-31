# -*- coding: utf-8 -*-
"""人声收束层：把「事件 + 段」算成「每个音该怎么发声」。

**现行结构（事件 + 段）**：MS 以事件为单位（一个事件 = 一个音），
每个音的发声内容来自挂在它下面的**段**——一段就是一个声母或一个韵母
（`initial` / `medial` / `nucleus` / `coda`），段**自带起止时间**。

收束层只做三件事：
  ① 读段（时间已经写好；缺时间的旧数据才按发音模板切）
  ② 按段文本查音色
  ③ 定音与音之间的转折

不经过汉字、不查字表、不做词变调。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pinyin as py
import vocal_turns as vt

RULES_VERSION = "vocal-1.0"


@dataclass
class SegmentPlan:
    kind: str
    text: str
    dur_us: int
    voiced: bool = True
    formants: tuple = ()
    noise: float = 0.0
    manner: str = ""
    place: str = ""
    aspirated: bool = False
    tone: int = 0          # 段级声调（0 = 沿用整音的声调）


@dataclass
class SyllablePlan:
    """**一个音**的发声计划（不是"一个字"）。"""
    char: str
    pinyin: str
    lexical_tone: int
    surface_tone: int
    word_id: int | None
    event_ids: list
    onset_us: int
    dur_us: int
    segments: list = field(default_factory=list)
    breathiness: float = 0.3
    melisma: bool = False       # 与前一音同 binding（拖腔）
    notes: list = field(default_factory=list)   # 本组全部音 [(onset_us, dur_us)]
    bind: str | None = None     # 绑定号（同一个字/发音结构的多段共享）
    combo: str | None = None
    row_id: str | None = None   # 本音对应的事件 id
    head: bool = True           # 本音是否带声母（= 是否重新起音的头）
    note_index: int = 0
    turn_kind: str | None = None    # 本音音头转折方式（None = 直接起音）
    turn_strength: int = 0
    overlap_us: int = 0         # 与前一音的重叠（>0 叠）
    xfade_us: int = 0
    gap_us: int = 0             # 与前一音之间的空隙（气口）
    row: object = None
    rows: list = field(default_factory=list)    # 本音的段行
    units: list = field(default_factory=list)   # 段的 (kind, text) 序列


@dataclass
class VocalPlan:
    rules_version: str = RULES_VERSION
    syllables: list = field(default_factory=list)   # 每个元素 = 一个音
    turns: list = field(default_factory=list)       # 音间转折
    issues: list = field(default_factory=list)


# ── 音色：段文本 → 参数 ─────────────────────────────────

def _phonetics(kind: str, text: str) -> dict:
    """段文本 → 音色参数。查不到就给空表（渲染层有缺省）。"""
    if kind == "initial":
        feat = py.INITIAL_FEATURES.get(text)
        if not feat:
            return {}
        manner, place, voiced, asp = feat
        noise = 0.0
        if manner == "fricative":
            noise = 0.7
        elif manner == "affricate":
            noise = 0.55
        elif manner == "plosive":
            noise = 0.35
        return {"manner": manner, "place": place, "voiced": bool(voiced),
                "aspirated": bool(asp), "noise": noise}
    if kind in ("medial", "nucleus"):
        fmt = py.VOWEL_FORMANTS.get(text)
        return {"formants": tuple(fmt) if fmt else (), "voiced": True}
    return {}


def _segment_rows(doc) -> dict:
    """event_id → 该音的段（按 index 升序）。"""
    by = {}
    for s in getattr(doc, "segments", []) or []:
        if not getattr(s, "event_id", ""):
            continue
        by.setdefault(s.event_id, []).append(s)
    for k in by:
        by[k].sort(key=lambda x: (int(x.index), x.kind))
    return by


def _segplan_from_rows(rows: list, note_us: int) -> list:
    """段 → 渲染用的段计划。

    段带着自己的起止时间（写谱侧按发音规则切好的）就用它；
    旧数据没有时间时才按类型模板分配。
    """
    spans = []
    for r in rows:
        st, en = int(getattr(r, "onset_us", 0) or 0), int(getattr(r, "release_us", 0) or 0)
        spans.append(en - st if (st and en and en > st) else 0)
    if all(s > 0 for s in spans):
        durs = spans
    else:
        durs = py.spread_durations([r.kind for r in rows], note_us)
    out = []
    for r, d in zip(rows, durs):
        info = _phonetics(r.kind, r.text)
        out.append(SegmentPlan(
            kind=r.kind, text=r.text, dur_us=int(d),
            voiced=info.get("voiced", True),
            formants=info.get("formants", ()),
            noise=info.get("noise", 0.0),
            manner=info.get("manner", ""),
            place=info.get("place", ""),
            aspirated=info.get("aspirated", False),
            tone=int(getattr(r, "tone", 0) or 0)))
    return out


def _constraints_for(doc, event) -> dict:
    """本音所属乐器的收束约束（人声取 vocal_fold 默认）。取不到就空表。"""
    inst = next((i for i in getattr(doc, "instruments", [])
                 if i.id == f"P{getattr(event, 'instrument_id', 0)}"), None)
    if inst is None:
        return {}
    try:
        import ms_instruments as reg
        return reg.resolve(inst.type, inst.subtype).get("constraints", {}) or {}
    except Exception:
        return {}


# ── 事件 + 段 → 每音计划 ────────────────────────────────

def _notes_from_segments(doc, plan: VocalPlan) -> list:
    by_event = _segment_rows(doc)
    events = sorted([e for e in doc.events if e.id in by_event],
                    key=lambda e: (e.onset_us, e.id))
    items = []
    prev_end = None
    prev_bind = None
    for e in events:
        rows = by_event[e.id]
        bind = rows[0].binding_id or rows[0].structure_id
        dur = max(1, (e.release_us if e.release_us is not None else e.onset_us) - e.onset_us)
        gap = 0 if prev_end is None else max(0, e.onset_us - prev_end)
        has_initial = any(r.kind == "initial" for r in rows)
        text = "".join(r.text for r in rows)
        tone = next((int(r.tone) for r in rows if int(r.tone or 0)), 0)
        if tone == 0:
            plan.issues.append({"code": "V-tone-missing", "severity": "warn",
                                "detail": f"{e.id} 的段没有声调，按平调处理"})
            tone = 1
        # 转折只发生在**同一 binding 的相邻音**之间；换 binding 就是新音节，直接起音。
        restart = any(int(getattr(r, "turn", 0) or 0) for r in rows[:1])
        same_group = prev_bind is not None and bind == prev_bind
        if not same_group:
            turn = {"kind": None, "strength": 0, "overlap_us": 0, "reason": "new-syllable"}
        elif restart:
            turn = {"kind": "restrike", "strength": vt.DEFAULT_STRENGTH["restrike"],
                    "overlap_us": 0, "reason": "段 turn=1"}
        elif gap >= vt.min_breath_us(_constraints_for(doc, e)):
            turn = {"kind": "breath", "strength": vt.DEFAULT_STRENGTH["breath"],
                    "overlap_us": 0, "reason": "gap"}
        elif gap == 0:
            turn = {"kind": "liaison", "strength": 0,
                    "overlap_us": min(30_000, max(5_000, dur // 10)), "reason": "abut"}
        else:
            turn = {"kind": "break", "strength": vt.DEFAULT_STRENGTH["break"],
                    "overlap_us": 0, "reason": "short-gap"}
        if turn["kind"]:
            plan.turns.append({"row_id": e.id, "bind": bind,
                               "kind": turn["kind"], "strength": turn["strength"],
                               "overlap_us": turn["overlap_us"], "gap_us": gap,
                               "reason": turn["reason"]})
        items.append({
            "event": e, "char": text, "pinyin": text, "tone": tone, "bind": bind,
            "event_ids": [e.id], "onset_us": e.onset_us, "dur_us": dur,
            "head": has_initial or not same_group, "note_index": len(items),
            "segments": _segplan_from_rows(rows, dur),
            "units": [(r.kind, r.text) for r in rows],
            "turn": turn, "gap_us": gap, "xfade_us": 0,
            "word_id": None, "notes": [(e.onset_us, dur)],
            "melisma": same_group, "rows": rows,
        })
        prev_end = (e.release_us if e.release_us is not None else e.onset_us)
        prev_bind = bind
    return items


def _emit(items: list, plan: VocalPlan) -> None:
    for it in items:
        turn = it.get("turn") or {}
        plan.syllables.append(SyllablePlan(
            char=it["char"], pinyin=it["pinyin"],
            lexical_tone=it["tone"], surface_tone=it["tone"],
            word_id=it.get("word_id"), event_ids=it["event_ids"],
            onset_us=it["onset_us"], dur_us=it["dur_us"],
            segments=it.get("segments") or [],
            breathiness=0.25 if it["tone"] == 5 else 0.35,
            melisma=bool(it.get("melisma")), notes=it["notes"],
            bind=it.get("bind"), combo=it.get("combo"),
            row_id=(it["event_ids"] or [None])[0],
            head=bool(it.get("head", True)), note_index=int(it.get("note_index", 0)),
            turn_kind=turn.get("kind"), turn_strength=int(turn.get("strength", 0)),
            overlap_us=int(turn.get("overlap_us", 0)),
            xfade_us=int(it.get("xfade_us", 0)),
            gap_us=int(it.get("gap_us", 0)),
            rows=it.get("rows", []),
            units=it.get("units", []),
        ))


def build_plan(doc) -> VocalPlan:
    """事件 + 段 → 每个音的发声计划。

    没有段但有哼唱声部时，按音高生成鼻音（`build_hum_plan`）。
    """
    plan = VocalPlan()
    segs = _segment_rows(doc)
    hum_ids = {inst.id for inst in getattr(doc, "instruments", [])
               if getattr(inst, "type", None) == "voice_hum"}
    if not segs and hum_ids:
        return build_hum_plan(doc)
    _emit(_notes_from_segments(doc, plan), plan)
    return plan


# ── 哼唱：无段，按音高生成单鼻音 ─────────────────────────

HUM_DEFAULT = "m"


def build_hum_plan(doc) -> VocalPlan:
    plan = VocalPlan()
    for e in doc.events:
        dur = (e.release_us if e.release_us is not None else e.onset_us) - e.onset_us
        tone = 5
        spans = [max(50_000, dur)]
        plan.syllables.append(SyllablePlan(
            char="哼", pinyin=HUM_DEFAULT, lexical_tone=tone, surface_tone=tone,
            word_id=None, event_ids=[e.id], onset_us=e.onset_us,
            dur_us=max(50_000, dur),
            segments=[SegmentPlan(kind="nucleus", text=HUM_DEFAULT,
                                  dur_us=spans[0],
                                  formants=py.VOWEL_FORMANTS.get(HUM_DEFAULT, (250, 1000, 2200)),
                                  tone=tone)],
            breathiness=0.30))
    return plan


def to_humming(doc, instrument_id: int = 1):
    """把一个乐器声部转成哼唱：换类型、清段。返回新文档（不改原对象）。"""
    import copy
    d = copy.deepcopy(doc)
    for inst in getattr(d, "instruments", []):
        if inst.id == f"P{instrument_id}":
            inst.type = "voice_hum"
            inst.subtype = None
    d.segments = [s for s in getattr(d, "segments", [])
                  if not any(e.id == s.event_id and e.instrument_id == instrument_id
                             for e in d.events)]
    return d
