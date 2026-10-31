# -*- coding: utf-8 -*-
"""G2 构造侧验收：构造/恢复路径验证（正例=结构一致；负例=真能触发失败）。

范围（SM0006 裁决）：验证从空 ScoreV02 程序化构造（追加/删改/往返）的结果与预期结构一致；
失败路径负向测试必须真能触发失败；不重证 G1。

运行：python g2_construction.py   （退出码 0 = 全过）
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import json
import os
import sys
from dataclasses import asdict, fields, is_dataclass

HERE = str(ROOT)
sys.path.insert(0, HERE)
from model_v02 import (  # noqa: E402
    AccidentalContext, ArticulationMark, NoteEvent, PedalMark, PitchSpell,
    RestEvent, ScoreV02, TieGroup, Tuplet,
)

FAILS = []


def check(name, cond, note=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" —— {note}" if note else ""))
    if not cond:
        FAILS.append(name)


def N(i, onset, dur, step="C", alter=0, octv=4, voice="1", staff="1", measure=1):
    return NoteEvent(id=f"n{i}", onset=onset, duration=dur, voice=voice,
                     staff=staff, measure=measure,
                     pitch=PitchSpell(step, alter, octv))


def R(i, onset, dur, voice="1", staff="1", measure=1):
    return RestEvent(id=f"r{i}", onset=onset, duration=dur, voice=voice,
                     staff=staff, measure=measure)


# ───────────────────────── P 正例：构造结果=预期结构 ─────────────────────────

def p_construct():
    s = ScoreV02(title="G2", grid_units_per_quarter=12)
    # 双声部：v1 同音 tie（C–C）+ E–F；v2 同起音和弦；v3 休止
    s.notes += [N(1, 0, 3, "C"), N(2, 3, 3, "C"), N(3, 6, 3, "E"), N(4, 9, 3, "F")]
    s.notes += [N(5, 0, 12, "C", octv=3, voice="2"), N(6, 0, 12, "E", octv=3, voice="2")]
    s.rests += [R(7, 0, 3, voice="3")]
    s.tie_groups.append(TieGroup(id="T1", member_ids=["n1", "n2"], voice="1"))
    s.tuplets.append(Tuplet(id="TP1", ratio=(3, 2), member_ids=["n1", "n2", "n3"]))
    s.articulations.append(ArticulationMark(id="A1", kind="staccato", target_ids=["n4"]))
    s.pedal_marks.append(PedalMark(id="P1", pedal_type="sostenuto",
                                   action_notated="start", onset=0, measure=1,
                                   target_scope=["n5", "n6"]))
    errs = s.validate()
    check("P1 构造合法结构 validate() 无错", not errs, str(errs[:4]))
    check("P2 同时事件集（和弦+休止）可表达",
          len(s.simultaneous(0)) == 4, f"n={len(s.simultaneous(0))}")
    spans = s.sustained_spans()
    check("P3 tie 组派生持续（不改写成员）",
          len(s.tie_groups) == 1 and len(s.tie_groups[0].member_ids) == 2 and spans,
          f"spans={spans}")
    check("P4 拍数派生 float 仅派生",
          abs(s.beats(3) - 0.25) < 1e-9, f"beats(3)={s.beats(3)}")
    # 临时记号语境（构造期行为）：同小节继承、换小节失效
    ctx = AccidentalContext()
    a1 = ctx.apply_notated(PitchSpell("F", 1, 4), "1", True)     # 谱面 F#
    a2 = ctx.apply_notated(PitchSpell("F", 0, 4), "1", False)    # 同小节无记号 → 继承 F#
    ctx.new_measure()
    a3 = ctx.apply_notated(PitchSpell("F", 0, 4), "1", False)    # 新小节 → 还原 F
    check("P5 临时记号语境：同小节继承/换小节失效",
          a1.alter == 1 and a2.alter == 1 and a3.alter == 0,
          f"{a1.alter},{a2.alter},{a3.alter}")
    return s


def p_restore(s):
    """恢复路径：序列化 → 反序列化 → 事实一致（记谱事实可恢复）。"""

    def dump(o):
        if is_dataclass(o):
            d = {"__cls__": type(o).__name__}
            for f in fields(o):
                d[f.name] = dump(getattr(o, f.name))
            return d
        if isinstance(o, (list, tuple)):
            return [dump(x) for x in o]
        return o

    def load(d):
        if isinstance(d, dict) and "__cls__" in d:
            cls = {"ScoreV02": ScoreV02, "NoteEvent": NoteEvent, "RestEvent": RestEvent,
                   "TieGroup": TieGroup, "Tuplet": Tuplet, "ArticulationMark": ArticulationMark,
                   "PedalMark": PedalMark, "PitchSpell": PitchSpell}[d["__cls__"]]
            kw = {k: load(v) for k, v in d.items() if k != "__cls__"}
            return cls(**kw)
        if isinstance(d, list):
            return [load(x) for x in d]
        return d

    raw = json.dumps(dump(s), ensure_ascii=False)
    s2 = load(json.loads(raw))
    check("R1 序列化往返可恢复", isinstance(s2, ScoreV02) and len(s2.notes) == len(s.notes),
          f"notes {len(s.notes)}->{len(s2.notes)}")
    check("R2 往返后 validate 仍无错", not s2.validate(), str(s2.validate()[:3]))
    same = all(a.pitch.semitone == b.pitch.semitone and a.onset == b.onset
               and a.duration == b.duration
               for a, b in zip(sorted(s.notes, key=lambda x: x.id),
                               sorted(s2.notes, key=lambda x: x.id)))
    check("R3 往返后记谱事实一致（音高/起点/时值）", same)


# ───────────────────────── N 负例：必须真能触发失败 ─────────────────────────

def n_overlap():
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [N(1, 0, 4, "C"), N(2, 2, 4, "D")]   # n2 在 n1 未结束时起音
    errs = s.validate()
    check("N1 同声部时间重叠必须被拒",
          any("重叠" in e for e in errs), str(errs[:3]))


def n_chord_allowed():
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [N(1, 0, 4, "C"), N(2, 0, 4, "E"), N(3, 0, 4, "G")]  # 同起音=和弦
    errs = s.validate()
    check("N1b 同起音和弦不误报（对照）", not errs, str(errs[:3]))


def n_tie_bad():
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [N(1, 0, 2, "C"), N(2, 2, 2, "D")]
    s.tie_groups.append(TieGroup(id="T1", member_ids=["n1", "n2"], voice="1"))
    errs = s.validate()
    check("N2 tie 成员音高不一致必须被拒", any("音高不一致" in e for e in errs), str(errs[:3]))
    s3 = ScoreV02(grid_units_per_quarter=4)
    s3.notes += [N(1, 0, 2, "C"), N(2, 3, 2, "C")]   # 时间断裂
    s3.tie_groups.append(TieGroup(id="T2", member_ids=["n1", "n2"], voice="1"))
    errs3 = s3.validate()
    check("N3 tie 成员时间断裂必须被拒", any("时间断裂" in e for e in errs3), str(errs3[:3]))


def n_misc():
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes.append(N(1, 0, 0, "C"))                  # 零时值
    s.notes.append(N(2, -1, 2, "D"))                 # 负起点
    s.tie_groups.append(TieGroup(id="T1", member_ids=["ghost"], voice="1"))
    s.articulations.append(ArticulationMark(id="A1", kind="staccato", target_ids=["ghost"]))
    s.pedal_marks.append(PedalMark(id="P1", pedal_type="sostenuto",
                                   action_notated="start", onset=0, measure=1))
    s.notes.append(NoteEvent(id="n3", onset=10, duration=2.5, voice="1",
                             staff="1", measure=3, pitch=PitchSpell("C", 0, 4)))
    errs = s.validate()
    joined = " | ".join(errs)
    check("N4 零时值/负起点/悬空 tie/悬空奏法/sostenuto 缺 scope/非整数时间 全部被拒",
          all(k in joined for k in ("时值必须为正", "起点不能为负", "成员 n" if False else "不存在",
                                    "目标", "target_scope", "整数网格")),
          joined[:180])


def main():
    print("== P 正例：构造与恢复 ==")
    s = p_construct()
    p_restore(s)
    print("\n== N 负例：失败路径必须真失败 ==")
    n_overlap()
    n_chord_allowed()
    n_tie_bad()
    n_misc()
    print("\n== 结果 ==")
    if FAILS:
        print(f"FAIL {len(FAILS)}: {FAILS}")
        return 1
    print("G2 构造侧验收全部通过（正例结构一致 + 负例真失败）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
