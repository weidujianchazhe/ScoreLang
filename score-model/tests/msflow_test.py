# -*- coding: utf-8 -*-
"""工具链协议（flow）：一次 run 走完六步、留档、且能被校验拦脏改。"""
from __future__ import annotations

import json
import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import msflow

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


lib = _Path(tempfile.mkdtemp())
res = msflow.run(ROOT / "samples" / "simple_melody.md", work_root=lib)
run_dir = _Path(res["run_dir"])

check("L1 六步都成功", [s["name"] for s in res["steps"]] == list(msflow.STEPS),
      str([s["name"] for s in res["steps"]]))
check("L2 六步产物齐全",
      all((run_dir / n).exists() for n in ("manifest.json", "piece.s02", "piece.s02x",
                                           "analysis.json", "report.md", "analysis.svg")),
      str(sorted(p.name for p in run_dir.iterdir())))
check("L3 特征向量维度固定", len(res["features"]) == 21, str(len(res["features"])))
check("L4 数据集有登记",
      any(json.loads(l)["run_id"] == res["run_id"]
          for l in (lib / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()),
      str(res["run_id"]))

chk = msflow.check(run_dir, work_root=lib)
check("L5 新 run 自检通过", chk["ok"], str(chk["problems"]))

# 脏改：改 report.md → sha 不符
rp = run_dir / "report.md"
orig = rp.read_text(encoding="utf-8")
rp.write_text(orig + "\n偷偷加一行\n", encoding="utf-8")
bad = msflow.check(run_dir, work_root=lib)
check("L6 产物被改会被抓", not bad["ok"] and any("sha" in p for p in bad["problems"]),
      str(bad["problems"]))
rp.write_text(orig, encoding="utf-8")

# 缺 manifest：模拟"没走 flow 的产出"
fake = lib / "runs" / "fake-run"
fake.mkdir(parents=True, exist_ok=True)
chk2 = msflow.check(fake, work_root=lib)
check("L7 没有 manifest 判不合格", not chk2["ok"] and any("manifest" in p for p in chk2["problems"]),
      str(chk2["problems"]))

# 缺步骤
m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
m2 = dict(m)
m2["steps"] = [s for s in m["steps"] if s["name"] != "report"]
(run_dir / "manifest.json").write_text(json.dumps(m2, ensure_ascii=False), encoding="utf-8")
chk3 = msflow.check(run_dir, work_root=lib)
check("L8 缺步骤判不合格", not chk3["ok"] and any("缺步骤" in p for p in chk3["problems"]),
      str(chk3["problems"]))
(run_dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

rows = msflow.list_runs(lib)
check("L9 list 能列出 run", any(r["run_id"] == res["run_id"] for r in rows), str(rows))

check("L10 两次 run 的 run_id 不同",
      msflow.run(ROOT / "samples" / "simple_melody.md", work_root=lib)["run_id"]
      != res["run_id"])

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
