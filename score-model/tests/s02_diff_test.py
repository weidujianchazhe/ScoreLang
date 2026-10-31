# -*- coding: utf-8 -*-
"""S02 改动对比（P8-1）：音符级 / 结构级 / 窗口级。"""
from __future__ import annotations

import copy
import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_diff

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def piece(bars=8):
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b in range(bars):
        for k in range(4):
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=b * 1920 + k * 480, duration=480, voice="RH",
                staff="treble", measure=b, pitch=spell(60 + k * 2),
                dynamics_permille=800, release_state="given", instrument_id=1))
    return s


a = piece()

# ── 1) 没有改动 ───────────────────────────────────────
same = s02_diff.compare(a, copy.deepcopy(a))
check("X1 无改动：三个计数都是 0",
      same["notes"]["added"] == same["notes"]["removed"] == same["notes"]["changed"] == 0,
      str(same["notes"])[:80])
check("X2 无改动：没有窗口变化", same["windows"]["movers"] == [],
      str(same["windows"]["movers"])[:80])

# ── 2) 改一个音的力度与音高 ───────────────────────────
b = copy.deepcopy(a)
old = b.notes[2]
b.notes[2] = copy.copy(old)
b.notes[2].dynamics_permille = 950
b.notes[2].pitch = spell(72)
diff = s02_diff.compare(a, b)
ch = [c for c in diff["notes"]["detail"]["changed"] if c["id"] == "L00000003"]
check("X3 检出被改的音", len(ch) == 1, str(diff["notes"]["detail"]["changed"])[:120])
check("X4 字段级 old/new 都有",
      ch and ch[0]["fields"]["permille"] == {"old": 800, "new": 950}
      and ch[0]["fields"]["semi"]["new"] == 72,
      str(ch[0]["fields"]) if ch else "")

# ── 3) 增删音 ─────────────────────────────────────────
c = copy.deepcopy(a)
c.notes = [n for n in c.notes if n.id != "L00000005"]
c.notes.append(mv.NoteEvent(
    id="L00009999", onset=0, duration=480, voice="RH", staff="treble", measure=0,
    pitch=spell(84), dynamics_permille=700, release_state="given", instrument_id=1))
diff2 = s02_diff.compare(a, c)
check("X5 检出删除", diff2["notes"]["removed"] == 1, str(diff2["notes"]))
check("X6 检出新增", diff2["notes"]["added"] == 1, str(diff2["notes"]))

# ── 4) 结构级 ─────────────────────────────────────────
pair = diff2["sections"]["pairs"]
check("X7 段落被配对", len(pair) >= 1 and all("label_a" in p for p in pair),
      str(pair)[:120])
check("X8 段落配对带小节范围", all("bars_a" in p for p in pair), str(pair[0]))

# ── 5) 窗口级 ─────────────────────────────────────────
movers = diff["windows"]["movers"]
check("X9 有窗口级变化（音区变了）",
      any("centroid" in m for m in movers), str(movers)[:160])

# ── 6) markdown ───────────────────────────────────────
md = s02_diff.to_markdown(diff, title="测试曲")
for sec in ("## 0. 概览", "## 1. 音符级改动", "## 2. 结构级变化",
            "## 3. 窗口级最大变化"):
    check(f"X10 markdown 含 {sec}", sec in md, md[:100])
check("X11 markdown 写出改动行", "L00000003" in md, md[:200])

# ── 7) 结构性大改：段落数变化 ─────────────────────────
d = piece(bars=20)
for i, n in enumerate(d.notes[:40]):
    d.notes[i].pitch = spell(60 + (i % 12) + 24)     # 整体抬高音区
diff3 = s02_diff.compare(a, d)
check("X12 段落数不同也能对比",
      diff3["sections"]["before"] >= 1 and diff3["sections"]["after"] >= 1,
      f"{diff3['sections']['before']} → {diff3['sections']['after']}")

# ── 8) 确定性 ─────────────────────────────────────────
check("X13 两次对比一致", s02_diff.compare(a, b) == s02_diff.compare(a, b))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
