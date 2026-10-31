# -*- coding: utf-8 -*-
"""参照比较（s02 compare）：不给分，只给分位。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import s02_compare as C

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def ref(name, **metrics):
    return {"name": name, "metrics": metrics}


# 参照集：structure 从 0.2 到 0.8 均匀分布（4 首）
refs = [ref("r1", structure=0.20), ref("r2", structure=0.40),
        ref("r3", structure=0.60), ref("r4", structure=0.80)]
res = C.compare({"structure": 0.50}, refs)
row = res["metrics"]["structure"]
check("R1 分位计算正确（0.5 落在 50% 附近）", 40 <= row["percentile"] <= 60, str(row))
check("R2 给出参照分位 p25/p50/p75",
      abs(row["ref"]["p50"] - 0.50) < 1e-9 and row["ref"]["p25"] == 0.35,
      str(row["ref"]))
check("R3 参照数量记录", res["ref_count"] == 4, str(res["ref_count"]))

low = C.compare({"structure": 0.1}, refs)["metrics"]["structure"]
high = C.compare({"structure": 0.9}, refs)["metrics"]["structure"]
check("R4 最低值分位 0%", low["percentile"] == 0.0, str(low["percentile"]))
check("R5 最高值分位 100%", high["percentile"] == 100.0, str(high["percentile"]))

missing = C.compare({"structure": None, "arc": 0.5}, refs)["metrics"]
check("R6 本曲缺该项 → 分位 None", missing["structure"]["percentile"] is None,
      str(missing["structure"]))
check("R7 参照缺该项 → 也 None", missing["arc"]["percentile"] is None,
      str(missing["arc"]))

partial = C.compare({"structure": 0.5}, [ref("a", structure=0.4),
                                         ref("b", structure=None),
                                         ref("c", structure=0.6)])
check("R8 参照缺值不计入分母", partial["metrics"]["structure"]["n"] == 2,
      str(partial["metrics"]["structure"]))

text = C.to_text(C.compare({"structure": 0.5, "arc": 0.9}, refs))
check("R9 文本含分位与 p25/p50/p75",
      "%" in text and "p25" in text and "structure" in text, text[:120])
check("R10 明确声明只给位置不给分",
      "分位" in res["note"] and "哪个好" in res["note"], res["note"])

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
