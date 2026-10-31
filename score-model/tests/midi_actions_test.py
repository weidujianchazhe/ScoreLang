# -*- coding: utf-8 -*-
"""MIDI 导出：演奏动作 / 弱音器 / 调音踏板 / 速度。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_midi as mm
import ms_semantics as ms

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


STEPS = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
         9: ("A", 0), 11: ("B", 0)}
TB = 500_000


def note(i, onset=0, dur=400_000, semi=60, inst=1):
    step, alter = STEPS[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=inst, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


def build(pedals=(), turns=(), insts=None):
    d = ev.MSDocument(events=[note(1), note(2, 500_000, 400_000, 64)],
                      instruments=insts or [ev.Instrument("P1", "violin", None, "strings_1")],
                      pedals=list(pedals), turns=list(turns))
    d.piano_count = len(d.instruments)
    d.constraint_mode = "single_piano" if d.piano_count == 1 else "n_pianos"
    return d


# 1) 动作写进 MIDI 文本 meta
data, rep = mm.write_midi_files(build(turns=[ev.TurnPoint("L00000001", "bow_up", 800)]),
                                time_base_us=TB)
check("M1 动作写文本 meta", b"turn:bow_up" in data[0])
check("M2 报告记录导出动作", rep["actions_exported"]
      and rep["actions_exported"][0]["kind"] == "bow_up", str(rep.get("actions_exported")))

# 2) 弱音器（无 CC）也不静默丢
data2, rep2 = mm.write_midi_files(
    build(pedals=[ev.PedalSegment(1, "sordino", 0, 900_000, 1000)]), time_base_us=TB)
check("M3 弱音器写文本 meta", b"sordino on" in data2[0])

# 3) 调音踏板写 RPN（fine tuning）
data3, _ = mm.write_midi_files(
    build(pedals=[ev.PedalSegment(1, "tuning", 0, 2_000_000, 0, "explicit", ("C",))],
          insts=[ev.Instrument("P1", "orchestral_harp")]), time_base_us=TB)
check("M4 调音写 RPN 1（fine tuning）",
      bytes([0xB0, 101, 0]) in data3[0] and bytes([0xB0, 100, 1]) in data3[0])
check("M5 调音同时写文本说明", b"tuning -100c" in data3[0])

# 4) 速度：可给 tempo_map（渐快渐进）
data4, _ = mm.write_midi_files(build(), time_base_us=TB)
check("M6 默认单 tempo", data4[0].count(b"\xFF\x51\x03") == 1,
      str(data4[0].count(b"\xFF\x51\x03")))
data5, _ = mm.write_midi_files(build(), time_base_us=TB,
                               tempo_map=[(0, 500_000), (480, 400_000), (960, 300_000)])
check("M7 给定 tempo_map → 多点速度（渐快）",
      data5[0].count(b"\xFF\x51\x03") == 3, str(data5[0].count(b"\xFF\x51\x03")))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
