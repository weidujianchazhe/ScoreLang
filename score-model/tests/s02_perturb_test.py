# -*- coding: utf-8 -*-
"""S02 局部扰动（L3）与 L3→L4 修正。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_perturb as pt
import s02_segment as seg
import s02_weights as wt

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    return mv.PitchSpell(step[0], 1 if "#" in step else 0, semi // 12 - 1)


def score_of(bars, *, voice="RH"):
    """bars: [(onset, [(semi, permille), ...])]，每项是一个时刻。"""
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for onset, notes in bars:
        for semi, pm in notes:
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=onset, duration=400, voice=voice,
                staff="treble", measure=onset // 1920, pitch=spell(semi),
                dynamics_permille=pm, release_state="given", instrument_id=1))
    return s


cfg = wt.load()
check("K1 权重含 perturb 段", "perturb" in cfg and cfg["perturb"]["accent_z"] > 0,
      str(cfg.get("perturb")))

# ── 1) 力度偏移 ───────────────────────────────────────
quiet = [(0, [(60, 600), (62, 600), (64, 600), (65, 600)])]
loud = [(0, [(60, 600), (62, 600), (64, 600), (65, 1500)])]
base = pt.analyze(score_of(quiet))
acc = pt.analyze(score_of(loud))
check("K2 平静谱无力度偏移", base["overall"]["by_kind"]["accent"] == 0,
      str(base["overall"]))
check("K3 一个突强被检出", acc["overall"]["by_kind"]["accent"] >= 1, str(acc["overall"]))
check("K4 突强指向具体音", any(e["kind"] == "accent" and e["note"] for e in acc["events"]),
      str(acc["events"][:2]))

# ── 2) 调外音 ─────────────────────────────────────────
diatonic = [(0, [(60, 800), (62, 800), (64, 800), (65, 800), (67, 800)])]
chroma = [(0, [(60, 800), (62, 800), (64, 800), (65, 800), (67, 800)]),
          (1920, [(60, 800), (61, 800), (62, 800), (64, 800)])]
check("K5 调内谱无调外音", pt.analyze(score_of(diatonic))["overall"]["by_kind"]["chromatic"] == 0,
      str(pt.analyze(score_of(diatonic))["overall"]))
check("K6 半音外音被检出", pt.analyze(score_of(chroma))["overall"]["by_kind"]["chromatic"] >= 1,
      str(pt.analyze(score_of(chroma))["overall"]))

# ── 3) 音区突变 ───────────────────────────────────────
steady = [(i * 480, [(60 + (i % 2), 800)]) for i in range(12)]
jump = steady[:8] + [(8 * 480, [(88, 800)])] + steady[9:]
check("K7 平稳旋律无音区突变",
      pt.analyze(score_of(steady))["overall"]["by_kind"]["register"] == 0,
      str(pt.analyze(score_of(steady))["overall"]))
check("K8 突然翻高被检出",
      pt.analyze(score_of(jump))["overall"]["by_kind"]["register"] >= 1,
      str(pt.analyze(score_of(jump))["overall"]))

# ── 4) 密度突变 ───────────────────────────────────────
sparse = [(0, [(60, 800)]), (1920, [(60, 800)])]
dense = sparse + [(3840, [(60, 800), (62, 800), (64, 800), (65, 800), (67, 800), (69, 800)])]
check("K9 密度突变被检出",
      pt.analyze(score_of(dense))["overall"]["by_kind"]["density"] >= 1,
      str(pt.analyze(score_of(dense))["overall"]))

# ── 5) L3 → L4：扰动抬高段落紧张度 ────────────────────
plain = score_of([(i * 1920, [(60, 600), (64, 600)]) for i in range(6)] +
                 [(i * 1920 + 960, [(62, 600), (65, 600)]) for i in range(6)])
noisy = score_of([(i * 1920, [(60, 600), (64, 600)]) for i in range(6)] +
                 [(i * 1920 + 960, [(62, 600), (65, 1500)]) for i in range(6)])
s_plain = seg.segment(plain, weights=cfg)
s_noisy = seg.segment(noisy, weights=cfg)
check("K10 段落带扰动计数",
      all("perturb" in x and "tension_adj" in x for x in s_plain["sections"]),
      str(s_plain["sections"][0]))
check("K11 扰动段紧张度不低于无扰动段",
      max(x["tension_adj"] for x in s_noisy["sections"])
      >= max(x["tension_adj"] for x in s_plain["sections"]),
      f"{max(x['tension_adj'] for x in s_noisy['sections'])} vs "
      f"{max(x['tension_adj'] for x in s_plain['sections'])}")
check("K12 segment 返回里带扰动明细", "perturb" in s_noisy and "events" in s_noisy["perturb"],
      str(list(s_noisy.get("perturb", {}))))

# ── 6) 阈值可换 & 确定性 ──────────────────────────────
strict = wt.load()
strict["perturb"]["accent_z"] = 99
check("K13 阈值调高后不报突强",
      pt.analyze(score_of(loud), weights=strict)["overall"]["by_kind"]["accent"] == 0,
      str(pt.analyze(score_of(loud), weights=strict)["overall"]))
check("K14 两次分析一致",
      pt.analyze(score_of(jump)) == pt.analyze(score_of(jump)))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
