# -*- coding: utf-8 -*-
"""S02 探针（评估）：逐小节特征、重复检测、确定性。"""
from __future__ import annotations

import json
import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_probe

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def score_with(notes) -> "mv.ScoreV02":
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano", "subtype": None,
                      "section": None}]
    s.notes = notes
    return s


def n(i, onset, dur, semi, vel=800):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    alter = 1 if "#" in step else 0
    return mv.NoteEvent(id=f"L{i:08d}", onset=onset, duration=dur, voice="RH",
                        staff="treble", measure=onset // 1920,
                        pitch=mv.PitchSpell(step[0], alter, semi // 12 - 1),
                        dynamics_permille=vel, release_state="given", instrument_id=1)


# ── 1) 密度 / 音区 / 力度 ────────────────────────────────
s = score_with([n(1, 0, 240, 60, 600), n(2, 240, 240, 62, 800),
                n(3, 480, 240, 64, 900), n(4, 720, 240, 65, 700)])
r = s02_probe.analyze(s)
b = r["bars"][0]
check("P1 窗口 1 有 4 个音", b["notes"] == 4, str(b))
check("P2 密度 = 每小节音数", b["density"] == 4.0, str(b["density"]))
check("P3 力度均值", abs(b["vel_mean"] - 750.0) < 1e-6, str(b["vel_mean"]))
check("P4 力度方差 > 0", b["vel_std"] > 50, str(b["vel_std"]))
check("P5 音区重心", abs(b["centroid"] - 62.75) < 1e-6, str(b["centroid"]))
check("P6 音域跨度", b["span"] == 5, str(b["span"]))
check("P7 音程序列", b["intervals"] == [2, 2, 1], str(b["intervals"]))

# ── 2) 同时发声（和弦）──────────────────────────────────
chord = score_with([n(1, 0, 480, 60), n(2, 0, 480, 64), n(3, 0, 480, 67)])
check("P8 三音和弦 poly=3", s02_probe.analyze(chord)["bars"][0]["poly"] == 3,
      str(s02_probe.analyze(chord)["bars"][0]["poly"]))

# ── 3) 重复检测：完全重复 / 移调 ────────────────────────
rep = score_with([
    n(1, 0, 240, 60), n(2, 240, 240, 62), n(3, 480, 240, 64),
    n(4, 1920, 240, 60), n(5, 2160, 240, 62), n(6, 2400, 240, 64),      # 同形同高
    n(7, 3840, 240, 63), n(8, 4080, 240, 65), n(9, 4320, 240, 67),      # 同形 +3
])
bars = s02_probe.analyze(rep)["bars"]
check("P9 第 2 小节判为完全重复", bars[1]["repeat"].startswith("exact:"), str(bars[1]["repeat"]))
check("P10 第 3 小节判为移调重复", bars[2]["repeat"].startswith("transposed:+3"),
      str(bars[2]["repeat"]))
check("P11 重复率 = 2/3", abs(s02_probe.analyze(rep)["summary"]["repeat_ratio"] - 0.667) < 0.01,
      str(s02_probe.analyze(rep)["summary"]["repeat_ratio"]))

# ── 4) 汇总与曲线 ──────────────────────────────────────
summ = s02_probe.analyze(rep)["summary"]
check("P12 汇总含音符/窗口/音域", summ["notes"] == 9 and summ["windows"] == 3
      and summ["pitch_range"] == (60, 67), str(summ))
check("P13 三条 ASCII 曲线非空",
      all(s02_probe.analyze(rep)["spark"][k] for k in ("density", "centroid", "vel_std")))
check("P14 空谱不崩", s02_probe.analyze(mv.ScoreV02())["bars"] == [])

# ── 5) 确定性 ─────────────────────────────────────────
j1 = json.dumps(s02_probe.analyze(rep), ensure_ascii=False, sort_keys=True)
j2 = json.dumps(s02_probe.analyze(rep), ensure_ascii=False, sort_keys=True)
check("P15 两次分析字节一致", j1 == j2)

# ── 6) 表格 ───────────────────────────────────────────
table = s02_probe.format_table(s02_probe.analyze(rep))
check("P16 表格有表头与行", "win" in table and "密度" in table and len(table.splitlines()) > 5)

# ── P17：中间空小节必须出现在 bars 里 ──
s_gap = score_with([n(1, 0, 240, 60), n(2, 2 * 1920, 240, 64)])
r_gap = s02_probe.analyze(s_gap)
check("P17 空窗口补齐", len(r_gap["bars"]) == 3
      and r_gap["bars"][1]["notes"] == 0,
      str([(b["window"], b["notes"]) for b in r_gap["bars"]]))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
