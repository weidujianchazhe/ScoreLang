# -*- coding: utf-8 -*-
"""S02 大数据校准（P5）：分位数 → 权重；校准后标签可解释地变化。"""
from __future__ import annotations

import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_calibrate as cal
import s02_segment as seg
import s02_weights as wt

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def piece(n_bars, notes_per_bar, base=60):
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b in range(n_bars):
        for k in range(notes_per_bar):
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=b * 1920, duration=300, voice="RH",
                staff="treble", measure=b, pitch=spell(base + (k % 7)),
                dynamics_permille=800, release_state="given", instrument_id=1))
    return s


# ── 1) 分位数 ─────────────────────────────────────────
check("C1 p50 取中位", cal.percentile([1, 2, 3, 4], 0.5) == 2.5,
      str(cal.percentile([1, 2, 3, 4], 0.5)))
check("C2 p25 线性插值", abs(cal.percentile([1, 2, 3, 4], 0.25) - 1.75) < 1e-9,
      str(cal.percentile([1, 2, 3, 4], 0.25)))
check("C3 单元素安全", cal.percentile([5], 0.9) == 5.0)
check("C4 空表返回 0", cal.percentile([], 0.5) == 0.0)

# ── 2) 收集与推导 ─────────────────────────────────────
sparse = piece(8, 2)
dense = piece(8, 12)
collected = cal.collect([sparse, dense])
derived = cal.derive(collected)
check("C5 收集到窗口与段落",
      derived["stats"]["samples"] > 0 and derived["stats"]["pieces"] == 2,
      str(derived["stats"]))
check("C6 score 有四个维度的 center/scale",
      set(derived["score"]) == {"tension_center", "tension_scale", "drive_center",
                                "drive_scale", "space_center", "space_scale",
                                "bright_center", "bright_scale"},
      str(sorted(derived["score"])))
check("C7 label 阈值有六个键",
      set(derived["label"]) == {"density_high", "density_low", "tension_high",
                                "tension_low", "centroid_high", "centroid_low"},
      str(sorted(derived["label"])))
check("C8 高阈值 > 低阈值",
      derived["label"]["density_high"] > derived["label"]["density_low"]
      and derived["label"]["tension_high"] > derived["label"]["tension_low"],
      str(derived["label"]))

# ── 3) 落盘后可被 weights 加载 ────────────────────────
tmp = _Path(tempfile.mkdtemp())
tp = cal.write_toml(derived, tmp / "w.toml", meta={"pieces": 2})
loaded = wt.load(tp)
check("C9 TOML 能被 load 覆盖",
      loaded["score"]["drive_center"] == derived["score"]["drive_center"]
      and loaded["label"]["density_high"] == derived["label"]["density_high"],
      str(loaded["score"]["drive_center"]))
check("C10 未校准的段保持默认",
      loaded["segment"]["min_section_bars"] == wt.DEFAULTS["segment"]["min_section_bars"]
      and loaded["perturb"]["accent_z"] == wt.DEFAULTS["perturb"]["accent_z"],
      str(loaded["segment"]))

# ── 4) 报告 ───────────────────────────────────────────
text = cal.report(derived, current=wt.load(), path=tmp / "r.md")
check("C11 报告含分布与对比表",
      "## 1. 分布" in text and "## 2. 阈值" in text
      and "score.drive_center" in text, text[:120])
check("C12 报告写出文件", (tmp / "r.md").exists())

# ── 5) 校准改变标签（可解释）──────────────────────────
before = seg.segment(dense, weights=wt.load())
after = seg.segment(dense, weights=loaded)
check("C13 校准后段的标签/依据有变化",
      [x["label"] for x in before["sections"]] != [x["label"] for x in after["sections"]]
      or before["sections"][0]["why"] != after["sections"][0]["why"],
      f"{[x['label'] for x in before['sections']]} vs {[x['label'] for x in after['sections']]}")

# ── 6) 确定性 ─────────────────────────────────────────
check("C14 两次校准结果一致",
      cal.derive(cal.collect([sparse, dense])) == cal.derive(cal.collect([sparse, dense])))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
