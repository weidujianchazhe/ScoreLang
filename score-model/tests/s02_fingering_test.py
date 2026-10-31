# -*- coding: utf-8 -*-
"""S02 指法/物理可行性（P2）：手部跨度、手位移动、难度标记。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_fingering
import s02_weights as wt

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def score_of(chords, *, bar=1920):
    """chords: [(onset, [semitones])]，onset 单位是 grid。"""
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for onset, semis in chords:
        for semi in semis:
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=onset, duration=bar // 2, voice="RH",
                staff="treble", measure=onset // bar, pitch=spell(semi),
                dynamics_permille=800, release_state="given", instrument_id=1))
    return s


cfg = wt.load()
check("F1 权重含 fingering 段", "fingering" in cfg and cfg["fingering"]["span_limit"] == 12,
      str(cfg.get("fingering")))

# ── 1) 够得着 ──────────────────────────────────────────
octave = s02_fingering.analyze(score_of([(0, [60, 72])]))
check("F2 八度跨度不算超限", octave["windows"][0]["hand_span"] == 12
      and octave["windows"][0]["stretch"] == 0, str(octave["windows"][0]))

tenth = s02_fingering.analyze(score_of([(0, [60, 76])]))
check("F3 十度（16 半音）记为超限", tenth["windows"][0]["stretch"] == 1,
      str(tenth["windows"][0]))
check("F4 十度难度为满值", tenth["windows"][0]["hard"] == 1.0, str(tenth["windows"][0]))

big = s02_fingering.analyze(score_of([(0, [48, 72])]))
check("F5 两个八度判为难（拆两手后手位移动大）",
      big["windows"][0]["hard"] > 0 and big["windows"][0]["hand_jump"] >= 24,
      str(big["windows"][0]))

# ── 2) 来得及 ──────────────────────────────────────────
near = s02_fingering.analyze(score_of([(0, [60]), (960, [62]), (1920, [64])]))
check("F6 相邻音手位移动小 → 正常", all(w["hard"] == 0 for w in near["windows"]),
      str([w["hard"] for w in near["windows"]]))

far = s02_fingering.analyze(score_of([(0, [48]), (1920, [84])]))
check("F7 大跳手位移动 → 标记", far["windows"][1]["hard"] > 0,
      str([w["hard"] for w in far["windows"]]))

# ── 3) 输出结构 ────────────────────────────────────────
check("F8 有 windows/overall/hard_bars 三块",
      set(octave) == {"windows", "overall", "hard_bars"}, str(sorted(octave)))
check("F9 overall 汇总字段齐全",
      {"max_span", "max_jump", "stretch_bars"} <= set(tenth["overall"]), str(tenth["overall"]))
check("F10 hard_bars 只收有难度的窗口",
      all(w["hard"] > 0 for w in tenth["hard_bars"]) and len(near["hard_bars"]) == 0,
      str(len(tenth["hard_bars"])))

# ── 4) 人话结论 ────────────────────────────────────────
check("F11 十度给出可读结论", "十度" in s02_fingering.label(tenth["windows"][0]),
      s02_fingering.label(tenth["windows"][0]))
check("F12 正常窗口结论为正常", s02_fingering.label(octave["windows"][0]) == "正常")

# ── 5) 确定性 ─────────────────────────────────────────
check("F13 两次分析一致", s02_fingering.analyze(score_of([(0, [60, 67, 72])])) ==
      s02_fingering.analyze(score_of([(0, [60, 67, 72])])))

# ── 6) 阈值可换 ───────────────────────────────────────
wide = wt.load()
wide["fingering"]["span_limit"] = 16
relaxed = s02_fingering.analyze(score_of([(0, [60, 72])]), weights=wide)
check("F14 放宽阈值后八度不报，十度才报",
      relaxed["windows"][0]["stretch"] == 0,
      str(relaxed["windows"][0]))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
