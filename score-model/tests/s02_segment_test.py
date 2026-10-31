# -*- coding: utf-8 -*-
"""S02 分段 / 标签 / 报告：规则层与文档生成。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_report
import s02_segment
import s02_weights as wt

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def spell(semi):
    step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
    alter = 1 if "#" in step else 0
    return mv.PitchSpell(step[0], alter, semi // 12 - 1)


def build(bars_notes, *, per_bar=4):
    """bars_notes: [(音高列表, 每音时值)]，每个元素是一小节。"""
    s = mv.ScoreV02(grid_units_per_quarter=480, time_beats=4, time_beat_type=4)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": None, "section": None}]
    i = 0
    for b, (semis, dur) in enumerate(bars_notes):
        t = b * 1920
        for semi in semis:
            i += 1
            s.notes.append(mv.NoteEvent(
                id=f"L{i:08d}", onset=t, duration=dur, voice="RH", staff="treble",
                measure=b, pitch=spell(semi), dynamics_permille=800,
                release_state="given", instrument_id=1))
            t += dur
    return s


cfg = wt.load()

# ── 1) 权重可覆盖 ─────────────────────────────────────
check("G1 默认权重有 segment/label/diagnose",
      set(cfg) >= {"segment", "label", "diagnose"} and cfg["segment"]["split_ratio"] > 0,
      str(sorted(cfg)))
tmp = _Path(tempfile_dir := __import__("tempfile").mkdtemp()) / "w.toml"
tmp.write_text("[segment]\nsplit_ratio = 0.02\n", encoding="utf-8")
cfg2 = wt.load(tmp)
check("G2 TOML 覆盖生效且其余保持默认",
      cfg2["segment"]["split_ratio"] == 0.02 and cfg2["segment"]["min_section_bars"]
      == cfg["segment"]["min_section_bars"], str(cfg2["segment"]))
check("G3 模板可导出", wt.dump_template(tmp).exists())

# ── 2) 分段：静→响的突变要切出来 ──────────────────────
quiet = [([60, 62], 480)] * 6                      # 6 小节稀疏
loud = [([60, 64, 67, 72], 240)] * 6               # 6 小节密集
s = build(quiet + loud)
res = s02_segment.segment(s, weights=cfg)
check("G4 至少切出 2 段", len(res["sections"]) >= 2, str([x["id"] for x in res["sections"]]))
first, last = res["sections"][0], res["sections"][-1]
check("G5 后半段密度更高",
      (last["features"]["density"] or 0) > (first["features"]["density"] or 0),
      f"{first['features']['density']} vs {last['features']['density']}")
check("G6 段覆盖全曲无空洞",
      res["sections"][0]["start_bar"] == 1
      and res["sections"][-1]["end_bar"] == res["bars"],
      str([(x["start_bar"], x["end_bar"]) for x in res["sections"]]))
check("G7 段不重叠且相接",
      all(a["end_bar"] + 1 == b["start_bar"] for a, b in
          zip(res["sections"], res["sections"][1:])))

# ── 3) 标签规则 ───────────────────────────────────────
def label_of(semis, dur, bars):
    return s02_segment.segment(build([(semis, dur)] * bars), weights=cfg)["sections"][0]["label"]

check("G8 稀疏低张力 → 留白/安静",
      label_of([60, 62], 960, 4) in ("留白", "安静", "陈述"),
      label_of([60, 62], 960, 4))
check("G9 极密 + 高张力 → 高潮/紧张/密集推进",
      label_of([60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71], 120, 4)
      in ("高潮", "紧张", "密集推进"),
      label_of([60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71], 120, 4))
check("G10 每段都有 label 与 why",
      all(x["label"] and x["why"] for x in res["sections"]))

# ── 4) 句读 ───────────────────────────────────────────
long_note = ([60], 1920 * 2)      # 一个音两小节
s2 = build([([60, 62], 480)] * 2 + [long_note] + [([64, 65], 480)] * 3)
res2 = s02_segment.segment(s2, weights=cfg)
check("G11 长音处产生句读", len(res2["phrases"]) >= 2, str(res2["phrases"]))
check("G12 句读都在某段内",
      all(any(p["section"] == x["id"] for x in res2["sections"]) for p in res2["phrases"]))

# ── 5) 报告 ───────────────────────────────────────────
text = s02_report.build(s, title="测试曲")
check("G13 报告有五个小标题",
      all(h in text for h in ("## 0. 摘要", "## 1. 结构", "## 2. 拓扑",
                              "## 3. 特征曲线", "## 4. 语义", "## 5. 诊断")),
      text[:200])
check("G14 报告含段落表与标签", "| 段 |" in text and first["label"] in text)
check("G15 报告确定性", s02_report.build(s, title="测试曲") == text)
check("G16 文本表格可读", "段  小节" in s02_segment.to_text(res))

# ── 6) 诊断规则可触发 ─────────────────────────────────
flat = build([([60, 62, 64, 65], 480)] * 8)          # 密度恒定
diag_text = s02_report.build(flat, title="平")
check("G17 平曲触发「密度极差小」诊断", "密度极差" in diag_text, diag_text[-300:])

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
