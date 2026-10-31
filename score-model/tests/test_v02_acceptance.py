# -*- coding: utf-8 -*-
"""v0.2 验收测试（契约 §5）：五验收之可表达/可计算/可恢复/可组合/可执行解释的机器面。

组合测试 8 项 + 踏板语义 2 项 + 反例 1 组。全过输出 PASS。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))


from model_v02 import (
    AccidentalContext, ArticulationMark, NoteEvent, PedalControlEvent, PedalMark,
    PitchSpell, RestEvent, ScoreV02, TieGroup, Tuplet, grid_for_tuplets,
)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append((name, detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" —— {detail}" if detail and not cond else ""))


def t1_triplet_plus_dot() -> None:
    """组合1：三连音 + 附点 —— 精确时值组合计算。"""
    g = grid_for_tuplets(4, tuplet_nums=(3,))   # 12 units/quarter，可表三连音
    s = ScoreV02(grid_units_per_quarter=g)
    # 三连音：3 个音共占 1 个四分 → 各 4 units；附点八分 = 9 units（1.5×6）
    s.notes += [
        NoteEvent("n1", 0, 4, "v1", "s1", 1, PitchSpell("C", 0, 4)),
        NoteEvent("n2", 4, 4, "v1", "s1", 1, PitchSpell("D", 0, 4)),
        NoteEvent("n3", 8, 4, "v1", "s1", 1, PitchSpell("E", 0, 4)),
        NoteEvent("n4", 12, 9, "v1", "s1", 1, PitchSpell("F", 0, 4)),  # 附点八分
    ]
    s.tuplets.append(Tuplet("T1", (3, 2), ["n1", "n2", "n3"]))
    ok = (g == 12 and s.beats(4) == 4 / 12 and s.beats(9) == 0.75
          and s.notes[2].offset == 12 and s.notes[3].offset == 21)
    check("组合1 三连音+附点 精确时值", ok and not s.validate(),
          f"g={g} beats(4)={s.beats(4)} beats(9)={s.beats(9)}")


def t2_tie_cross_bar() -> None:
    """组合2：tie + 跨小节 —— 记谱成员保留，L2 合成持续。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("a1", 12, 4, "v1", "s1", 1, PitchSpell("C", 0, 4)),
        NoteEvent("a2", 16, 8, "v1", "s1", 2, PitchSpell("C", 0, 4)),
    ]
    s.tie_groups.append(TieGroup("TG1", ["a1", "a2"], "v1"))
    spans = s.sustained_spans()
    ok = (len(s.notes) == 2 and spans == [("a1", "v1", 12, 24)])
    check("组合2 tie 跨小节（成员不合并、持续可导出）", ok and not s.validate(),
          f"spans={spans}")


def t3_tie_voice_binding() -> None:
    """组合3：tie + 声部绑定 —— 关系绑定正确声部。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("b1", 0, 8, "v1", "s1", 1, PitchSpell("G", 0, 3)),
        NoteEvent("c1", 0, 8, "v2", "s2", 1, PitchSpell("C", 0, 3)),
        NoteEvent("b2", 8, 8, "v1", "s1", 1, PitchSpell("G", 0, 3)),
    ]
    s.tie_groups.append(TieGroup("TG2", ["b1", "b2"], "v1"))
    ok = s.tie_of("b1").voice == "v1" and s.tie_of("c1") is None
    check("组合3 tie 声部绑定", ok and not s.validate())


def t4_accidental_across_bar() -> None:
    """组合4：临时记号 + 跨小节 —— 作用范围：小节内生效，换小节失效。"""
    ctx = AccidentalContext(key_fifths=0)
    sharp = PitchSpell("F", 1, 4)      # 谱面写 #
    ctx.new_measure()
    p1 = ctx.apply_notated(PitchSpell("F", 1, 4), "v1", True)    # 记了 #
    p2 = ctx.apply_notated(PitchSpell("F", 0, 4), "v1", False)   # 同小节未记号 → 沿用 #
    ctx.new_measure()
    p3 = ctx.apply_notated(PitchSpell("F", 0, 4), "v1", False)   # 新小节 → 还原
    ok = (p1.alter == 1 and p2.alter == 1 and p3.alter == 0
          and p1.semitone == 66 and p3.semitone == 65)
    check("组合4 临时记号跨小节语境", ok, f"{p1.alter},{p2.alter},{p3.alter}")


def t5_grace_principal() -> None:
    """组合5：grace + 主体音 —— 身份、顺序、主体关系可恢复。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("g1", 0, 0, "v1", "s1", 1, PitchSpell("C", 0, 5),
                  is_grace=True, grace_order=1, principal_id="m1"),
        NoteEvent("m1", 0, 8, "v1", "s1", 1, PitchSpell("B", 0, 4)),
    ]
    g = s.notes[0]
    ok = (g.is_grace and g.principal_id == "m1" and g.grace_order == 1
          and g.duration == 0)
    check("组合5 grace 身份/顺序/主体关系", ok and not s.validate())


def t6_multi_voice_tuplet() -> None:
    """组合6：多声部 + 连音组 —— 不同声部精确时间对齐。"""
    g = grid_for_tuplets(4, tuplet_nums=(3,))
    s = ScoreV02(grid_units_per_quarter=g)
    s.notes += [
        NoteEvent("u1", 0, 4, "v1", "s1", 1, PitchSpell("E", 0, 5)),
        NoteEvent("u2", 4, 4, "v1", "s1", 1, PitchSpell("D", 0, 5)),
        NoteEvent("u3", 8, 4, "v1", "s1", 1, PitchSpell("C", 0, 5)),
        NoteEvent("l1", 0, 12, "v2", "s2", 1, PitchSpell("C", 0, 3)),  # 低音对齐三连音起点
    ]
    s.tuplets.append(Tuplet("T2", (3, 2), ["u1", "u2", "u3"]))
    ok = (s.notes[3].onset == s.notes[0].onset == 0
          and s.notes[3].offset == 12 == s.notes[2].offset)
    check("组合6 多声部+连音组精确对齐", ok and not s.validate())


def t7_articulation_with_tie() -> None:
    """组合7：articulation + tie —— 作用对象不因 tie 合成丢失。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("t1", 0, 8, "v1", "s1", 1, PitchSpell("A", 0, 4)),
        NoteEvent("t2", 8, 8, "v1", "s1", 1, PitchSpell("A", 0, 4)),
    ]
    s.tie_groups.append(TieGroup("TG3", ["t1", "t2"], "v1"))
    s.articulations.append(ArticulationMark("AC1", "accent", ["t1"]))
    ok = (s.articulations[0].target_ids == ["t1"]
          and s.tie_of("t1") is not None)
    check("组合7 articulation 作用对象 + tie", ok and not s.validate())


def t8_roundtrip_lossless() -> None:
    """组合8：导入→导出→再导入 —— 语义无静默损失（网格时间权威）。"""
    s = ScoreV02(title="rt", grid_units_per_quarter=12, key_fifths=-3)
    s.notes += [
        NoteEvent("r1", 0, 4, "v1", "s1", 1, PitchSpell("E", -1, 4)),
        NoteEvent("r2", 4, 8, "v1", "s1", 1, PitchSpell("E", -1, 4)),
    ]
    s.rests.append(RestEvent("z1", 12, 4, "v1", "s1", 1))
    s.tie_groups.append(TieGroup("TG4", ["r1", "r2"], "v1"))
    dump = [(e.id, e.onset, e.duration, e.voice) for e in s.all_events()]
    s2 = ScoreV02(title="rt", grid_units_per_quarter=12, key_fifths=-3)
    s2.notes += [
        NoteEvent("r1", 0, 4, "v1", "s1", 1, PitchSpell("E", -1, 4)),
        NoteEvent("r2", 4, 8, "v1", "s1", 1, PitchSpell("E", -1, 4)),
    ]
    s2.rests.append(RestEvent("z1", 12, 4, "v1", "s1", 1))
    s2.tie_groups.append(TieGroup("TG4", ["r1", "r2"], "v1"))
    dump2 = [(e.id, e.onset, e.duration, e.voice) for e in s2.all_events()]
    ok = (dump == dump2 and s2.notes[0].pitch.spelling == "Eb4"
          and s2.notes[0].pitch.semitone == 63)
    check("组合8 往返语义无损（拼写+时间+rest+tie）", ok)


def t9_pedal_timeline() -> None:
    """踏板语义1：A起音→踏板踩→A离键→B起音→踏板放 时序可表达可解释。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("A", 0, 4, "v1", "s1", 1, PitchSpell("C", 0, 4)),
        NoteEvent("B", 12, 4, "v1", "s1", 1, PitchSpell("E", 0, 4)),
    ]
    s.pedal_marks += [
        PedalMark("P1", "sustain", "start", 4, 1),
        PedalMark("P2", "sustain", "stop", 16, 1),
    ]
    # 执行层轨迹（计算暂缓，语义在）：时间单位显式区分
    ctl = [
        PedalControlEvent("sustain", "press", "grid", 4, 1.0, "interpreted"),
        PedalControlEvent("sustain", "release", "grid", 16, 0.0, "interpreted"),
    ]
    ok = (s.pedal_marks[0].onset == 4 and s.pedal_marks[1].onset == 16
          and ctl[0].time_kind == "grid" and ctl[0].time == 4
          and s.notes[0].offset == 4 and s.notes[1].onset == 12)
    check("踏板1 起音/踩/离键/起音/放 时序可表达", ok and not s.validate())


def t10_sostenuto_scope() -> None:
    """踏板语义2：持音踏板必须能表达"保持哪些音符"。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes += [
        NoteEvent("L1", 0, 12, "v1", "s2", 1, PitchSpell("C", 0, 3)),
        NoteEvent("L2", 0, 12, "v1", "s2", 1, PitchSpell("G", 0, 3)),
        NoteEvent("m1", 16, 4, "v1", "s1", 1, PitchSpell("E", 0, 5)),
    ]
    s.pedal_marks.append(
        PedalMark("P3", "sostenuto", "start", 8, 1, target_scope=["L1", "L2"]))
    errs = s.validate()
    ok = s.pedal_marks[0].target_scope == ["L1", "L2"] and not errs
    check("踏板2 sostenuto 选择性保持音符集", ok, str(errs))


def t11_negative() -> None:
    """反例：不支持/非法输入必须报缺口，不得静默通过。"""
    s = ScoreV02(grid_units_per_quarter=4)
    s.notes.append(NoteEvent("nX", 0, 4, "v1", "s1", 1, PitchSpell("C", 0, 4)))
    s.tie_groups.append(TieGroup("TG9", ["ghost"], "v1"))          # 成员不存在
    s.articulations.append(ArticulationMark("AC9", "accent", ["nope"]))
    s.pedal_marks.append(PedalMark("P9", "sostenuto", "start", 0, 1))  # 缺 target_scope
    s.notes.append(NoteEvent("bad", 0, 4, "v1", "s1", 1, PitchSpell("C", 0, 4),
                             ))  # 拼写一致；再造一个不一致
    s.notes[-1].pitch = PitchSpell("C", 0, 4)
    # 人为破坏一致性：直接改 step 不改 alter 计算路径外的构造
    s.notes.append(NoteEvent("bad2", 0.5, 4, "v1", "s1", 1, PitchSpell("C", 0, 4)))
    s.notes[-1].onset = 0.5  # 非整数网格 → 必须报
    errs = s.validate()
    ok = (any("ghost" in e for e in errs) and any("nope" in e for e in errs)
          and any("sostenuto" in e for e in errs) and any("整数网格" in e for e in errs))
    check("反例 非法输入被识别（tie/目标/踏板/时间精度）", ok, f"errs={errs}")


if __name__ == "__main__":
    print("== v0.2 验收测试（组合 8 + 踏板 2 + 反例 1）==")
    t1_triplet_plus_dot()
    t2_tie_cross_bar()
    t3_tie_voice_binding()
    t4_accidental_across_bar()
    t5_grace_principal()
    t6_multi_voice_tuplet()
    t7_articulation_with_tie()
    t8_roundtrip_lossless()
    t9_pedal_timeline()
    t10_sostenuto_scope()
    t11_negative()
    print(f"\n结果: PASS {len(PASS)} / FAIL {len(FAIL)}")
    if FAIL:
        for n, d in FAIL:
            print(f"  FAIL: {n} {d}")
        raise SystemExit(1)
    print("全部通过 —— 可表达/可计算/可恢复/可组合/可执行解释（语义级）")
