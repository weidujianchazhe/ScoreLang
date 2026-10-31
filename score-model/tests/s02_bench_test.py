# -*- coding: utf-8 -*-
"""P7 性能基线工具的最小验证（不做性能断言，只保证能量且结构对）。"""
from __future__ import annotations

import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms
import ms_io
import s02_bench

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


SAMPLE = ROOT / "samples" / "simple_melody.md"
doc = ms.load(SAMPLE)
row = s02_bench.bench_doc(doc)

check("P1 各层都跑出了数字",
      {"notes", "project", "probe", "harmony", "perturb", "fingering", "segment",
       "index", "report", "render_svg"} <= set(row), str(sorted(row)))
check("P2 音符数正确", row["notes"] == len(ms.load(SAMPLE).events))
check("P3 时间非负", all(v >= 0 for k, v in row.items() if k != "notes"),
      str({k: v for k, v in row.items() if k != "notes"}))
check("P4 有增量数字", "index_incremental" in row, str(sorted(row)))

md = s02_bench.to_markdown([{**row, "file": "x.ms"}])
check("P5 markdown 有表头与数据行",
      "| 曲目 |" in md and "| x.ms |" in md, md.splitlines()[2][:60])

tmp = _Path(tempfile.mkdtemp())
rows = [{"file": "a.ms", "notes": 10, "project": 0.1}]
(t2 := s02_bench.to_markdown(rows))
check("P6 缺列用 - 占位", "| a.ms | 10 | 0.1 | - |" in t2, t2.splitlines()[2])

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
