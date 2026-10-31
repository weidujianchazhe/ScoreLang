# -*- coding: utf-8 -*-
"""张力 / 协和 / 声部干涉（固定常数，零权重）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_harmony as hm

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def mk(semis, durs=None, voice="RH"):
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    durs = durs or [480] * len(semis)
    t = 0
    for i, (semi, d) in enumerate(zip(semis, durs)):
        step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
        alter = 1 if "#" in step else 0
        s.notes.append(mv.NoteEvent(
            id=f"L{i + 1:08d}", onset=t, duration=d, voice=voice, staff="treble",
            measure=t // 1920, pitch=mv.PitchSpell(step[0], alter, semi // 12 - 1),
            dynamics_permille=800, release_state="given", instrument_id=1))
        t += d
    return s


def chord(semis, voice="RH"):
    s = mk([], voice=voice)
    for i, semi in enumerate(semis):
        step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
        alter = 1 if "#" in step else 0
        s.notes.append(mv.NoteEvent(
            id=f"L{i + 1:08d}", onset=0, duration=480, voice=voice, staff="treble",
            measure=0, pitch=mv.PitchSpell(step[0], alter, semi // 12 - 1),
            dynamics_permille=800, release_state="given", instrument_id=1))
    return s


# ── 1) 协和度常数表 ───────────────────────────────────
check("H1 纯五度最协和", hm.consonance(7) == 1.0, str(hm.consonance(7)))
check("H2 三全音最不协和", hm.consonance(6) < 0.15, str(hm.consonance(6)))
check("H3 八度等价", hm.consonance(12) == hm.consonance(0))
check("H4 小数按 mod 12", hm.consonance(19) == hm.consonance(7))

# ── 2) 纵向张力 ───────────────────────────────────────
major = chord([60, 64, 67])
dim = chord([60, 63, 66])
check("H5 大三和弦张力低", hm.vertical_tension(major.notes) < 0.3,
      str(hm.vertical_tension(major.notes)))
check("H6 减三和弦张力高", hm.vertical_tension(dim.notes) > hm.vertical_tension(major.notes),
      f"{hm.vertical_tension(dim.notes)} vs {hm.vertical_tension(major.notes)}")
check("H7 单音无纵向张力", hm.vertical_tension([mv.NoteEvent(
    id="L00000001", onset=0, duration=480, voice="RH", staff="treble", measure=0,
    pitch=mv.PitchSpell("C", 0, 4), dynamics_permille=800, release_state="given",
    instrument_id=1)]) == 0.0)

# ── 3) 横向跳进 ───────────────────────────────────────
step_ = hm.leap_tension(2)
leap_ = hm.leap_tension(9)
far = hm.leap_tension(19)
check("H8 级进 < 跳进 < 超八度", step_ < leap_ < far, f"{step_} {leap_} {far}")
check("H9 大跳张力有上限", hm.leap_tension(60) <= 1.0, str(hm.leap_tension(60)))

def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    alter = 1 if "#" in step else 0
    return mv.PitchSpell(step[0], alter, semi // 12 - 1)


# ── 4) 声部干涉 ───────────────────────────────────────
two = mk([60, 62, 64])
for i, semi in enumerate([72, 70, 68]):
    two.notes.append(mv.NoteEvent(
        id=f"L1{i + 1:07d}", onset=i * 480, duration=480, voice="LH", staff="bass",
        measure=0, pitch=spell(semi), dynamics_permille=800,
        release_state="given", instrument_id=1))
inter = hm.interference(two)
check("H10 反向进行被识别", inter["contrary"] >= 2, str(inter))

same = mk([60, 62, 64])
for i, semi in enumerate([72, 74, 76]):
    same.notes.append(mv.NoteEvent(
        id=f"L1{i + 1:07d}", onset=i * 480, duration=480, voice="LH", staff="bass",
        measure=0, pitch=spell(semi), dynamics_permille=800,
        release_state="given", instrument_id=1))
check("H11 同向进行被识别", hm.interference(same)["similar"] >= 2, str(hm.interference(same)))

# ── 5) 窗口聚合 ───────────────────────────────────────
a = hm.analyze(same)
check("H12 逐窗口有张力字段",
      set(a["windows"][0]) >= {"window", "v_tension_mean", "leap_mean", "chromatic"},
      str(a["windows"][0]))
check("H13 overall 有聚合值", "v_tension" in a["overall"] and "contrary" in a["overall"],
      str(a["overall"]))
check("H14 确定性", hm.analyze(same) == hm.analyze(same))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
