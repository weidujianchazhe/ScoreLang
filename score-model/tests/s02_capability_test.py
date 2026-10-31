# -*- coding: utf-8 -*-
"""演奏能力覆盖：可用 vs 已用、缺口提示、写法示例、乐器清单。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_author as au
import s02_capability as cap

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def build_doc(*, with_turns=False, with_pedal=False, with_curve=False, only_piano=False):
    used = set()
    events = []
    insts = [au.make_instrument("P1", "acoustic_grand_piano")]
    if not only_piano:
        insts.append(au.make_instrument("P2", "violin"))
    for i in range(8):
        evs = au.write_note(onset_us=i * 500_000, duration_us=400_000, semitone=60,
                            instrument_id=1, permille=800, used_ids=used)
        events += evs
        used.update(e.id for e in evs)
    if not only_piano:
        for i in range(8):
            evs = au.write_note(onset_us=i * 500_000, duration_us=400_000,
                                semitone=72 + (i % 3), instrument_id=2, permille=700,
                                used_ids=used)
            events += evs
            used.update(e.id for e in evs)
    pedals, turns, curves = [], [], []
    if with_pedal:
        pedals.append(au.write_pedal(piano_id=1, kind="sustain", start_us=0,
                                     end_us=2_000_000, depth_permille=900))
    if with_turns:
        # 转折要有"前一个音"：挂在该乐器第二个音上
        turns.append(au.write_turn(event_id=events[1].id, kind="retrigger"))
        if not only_piano:
            turns.append(au.write_turn(event_id=events[9].id, kind="bow_change"))
    if with_curve:
        import ms_events as ev
        curves.append(ev.CurvePoint(instrument_id=1, param="dynamics",
                                    time_us=0, value=500, ramp=0))
    doc = au.to_document(events, instruments=insts, pedals=pedals, turns=turns,
                         piano_count=2)
    if curves:
        doc.curves = curves          # to_document 暂不收 curves，建完文档再挂
    return doc


rep = cap.analyze(build_doc())
check("C1 两件乐器都识别", rep["summary"]["instrument_count"] == 2,
      str(rep["summary"]["instrument_count"]))
check("C2 机制有 hammered + bowed",
      set(rep["summary"]["mechanisms"]) == {"hammered_string", "bowed_string"},
      str(rep["summary"]["mechanisms"]))
check("C3 什么都没用 → 缺口全列",
      any("转折" in g for g in rep["summary"]["gaps"])
      and any("踏板" in g for g in rep["summary"]["gaps"])
      and any("曲线" in g for g in rep["summary"]["gaps"]),
      str(rep["summary"]["gaps"]))

piano = next(x for x in rep["instruments"] if x["type"] == "acoustic_grand_piano")
violin = next(x for x in rep["instruments"] if x["type"] == "violin")
check("C4 钢琴可用踏板含 sostenuto/una_corda",
      "sostenuto" in piano["available"]["pedals"] and "una_corda" in piano["available"]["pedals"],
      str(piano["available"]["pedals"]))
check("C5 小提琴可用转折含 pizz/arco",
      "pizz" in violin["available"]["turns"] and "arco" in violin["available"]["turns"],
      str(violin["available"]["turns"]))
check("C6 小提琴不该有 key_noise（那是钢琴的）",
      "key_noise" not in violin["available"]["turns"],
      str(violin["available"]["turns"]))

rep2 = cap.analyze(build_doc(with_turns=True, with_pedal=True, with_curve=True))
piano2 = next(x for x in rep2["instruments"] if x["type"] == "acoustic_grand_piano")
violin2 = next(x for x in rep2["instruments"] if x["type"] == "violin")
check("C7 已用转折被记录", "retrigger" in piano2["used"]["turns"], str(piano2["used"]))
check("C8 已用转折不再出现在未用里", "retrigger" not in piano2["unused"]["turns"],
      str(piano2["unused"]["turns"][:6]))
check("C9 已用小提琴换弓", "bow_change" in violin2["used"]["turns"], str(violin2["used"]))
check("C10 已用踏板/曲线被记录",
      "sustain" in piano2["used"]["pedals"] and "dynamics" in piano2["used"]["curves"],
      str(piano2["used"]))
check("C11 缺口减少（无转折/无踏板提示消失）",
      not any("没有任何演奏转折" in g for g in rep2["summary"]["gaps"]),
      str(rep2["summary"]["gaps"]))
check("C12 写法示例给出 API",
      any("write_turn" in h["how"] for h in violin["hints"])
      and any("write_pedal" in h["how"] for h in piano["hints"]),
      str(piano["hints"][:2]))

single = cap.analyze(build_doc(only_piano=True))
check("C13 单乐器提示编制单调",
      any("1 件乐器" in g for g in single["summary"]["gaps"]),
      str(single["summary"]["gaps"]))

rows = cap.available_instruments()
check("C14 乐器清单位数 > 100", len(rows) > 100, str(len(rows)))
check("C15 清单含音域与机制",
      all(r.get("range") and r.get("mechanism") for r in rows),
      str(rows[0]))
piano_only = cap.available_instruments(family="piano")
check("C16 可按族过滤", piano_only and all(r["family"] == "piano" for r in piano_only),
      str(len(piano_only)))
check("C17 确定性", cap.analyze(build_doc()) == cap.analyze(build_doc()))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
