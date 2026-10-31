# -*- coding: utf-8 -*-
"""基线分布工具：多首曲子同一套特征 + 汇总表。"""
from __future__ import annotations

import json
import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import tempfile

import ms_events as ev
import ms_io
import ms_semantics as ms
import s02_baseline

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def make_doc(semis):
    events = []
    for i, semi in enumerate(semis):
        step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
        alter = 1 if "#" in step else 0
        events.append(ev.Event(
            id=f"L{i + 1:08d}", instrument_id=1, onset_us=i * 480_000,
            release_us=(i + 1) * 480_000,
            pitch=ev.Pitch(step[0], alter, semi // 12 - 1, semi),
            release_state="given",
            dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured")))
    return ev.MSDocument(events=events)


tmp = _Path(tempfile.mkdtemp())
# 造两首小曲：一首 4 个音、一首 8 个音（密度不同）
for name, semis in (("a", [60, 62, 64, 65]), ("b", [60, 62, 64, 65, 67, 69, 71, 72])):
    (tmp / f"{name}.ms").write_text(ms_io.dump(make_doc(semis)), encoding="utf-8")

rows = s02_baseline.run([tmp / "a.ms", tmp / "b.ms"], tmp / "out", time_base_us=500_000)
check("B1 两首都跑出结果", len(rows) == 2, str([r["name"] for r in rows]))
check("B2 汇总字段齐全",
      set(rows[0]) >= {"name", "notes", "sections", "density_mean", "centroid_mean",
                       "tension_mean", "leap_mean", "repeat_ratio", "labels"},
      str(sorted(rows[0])))
check("B3 音符数正确", rows[0]["notes"] == 4 and rows[1]["notes"] == 8,
      str([r["notes"] for r in rows]))
check("B4 密度与音符数一致（4 音/1 窗口 = 4.0）", rows[0]["density_mean"] == 4.0,
      str(rows[0]["density_mean"]))
check("B5 汇总文件写出", (tmp / "out" / "summary.md").exists()
      and (tmp / "out" / "summary.json").exists())
check("B6 每首都有 probe.json", (tmp / "out" / "a.probe.json").exists()
      and (tmp / "out" / "b.probe.json").exists())
check("B7 汇总表含表头与两行", (tmp / "out" / "summary.md").read_text(encoding="utf-8").count("| a |") == 1)
check("B8 确定性", s02_baseline.run([tmp / "a.ms", tmp / "b.ms"], tmp / "out2",
                                    time_base_us=500_000) == rows)
check("B9 JSON 可解析",
      json.loads((tmp / "out" / "summary.json").read_text(encoding="utf-8"))[0]["name"] == "a")
check("B10 跳进有值（非全 0）", any(r["leap_mean"] > 0 for r in rows),
      str([r["leap_mean"] for r in rows]))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
