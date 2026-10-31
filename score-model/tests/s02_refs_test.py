# -*- coding: utf-8 -*-
"""参照曲目库（P8-3）：登记 / 列表 / 校准 / 版本化 / 留一法稳定性。"""
from __future__ import annotations

import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_io
import ms_semantics as ms
import s02_refs

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def make_ms(path, bars, per_bar, base=60):
    events = []
    i = 0
    for b in range(bars):
        for k in range(per_bar):
            i += 1
            semi = base + (k % 5)
            step = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][semi % 12]
            events.append(ev.Event(
                id=f"L{i:08d}", instrument_id=1,
                onset_us=b * 1_920_000 + k * 240_000,
                release_us=b * 1_920_000 + k * 240_000 + 240_000,
                pitch=ev.Pitch(step[0], 1 if "#" in step else 0, semi // 12 - 1, semi),
                release_state="given",
                dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured")))
    path.write_text(ms_io.dump(ev.MSDocument(events=events)), encoding="utf-8")
    return path


tmp = _Path(tempfile.mkdtemp())
refroot = tmp / "refs"
src1 = make_ms(tmp / "a.ms", 6, 4, 60)
src2 = make_ms(tmp / "b.ms", 10, 8, 67)

# ── 1) 登记 ───────────────────────────────────────────
e1 = s02_refs.add(src1, title="甲", root=refroot)
e2 = s02_refs.add(src2, title="乙", root=refroot)
check("R1 登记返回事件数", e1["notes"] > 0 and e2["notes"] > e1["notes"],
      f"{e1['notes']} / {e2['notes']}")
check("R2 文件已复制进库", (refroot / "a.ms").exists() and (refroot / "b.ms").exists())
check("R3 manifest 可读", len(s02_refs.load_manifest(refroot)) == 2,
      str(s02_refs.load_manifest(refroot)))
check("R4 manifest 是合法 TOML", (refroot / "manifest.toml").exists()
      and "[[" in (refroot / "manifest.toml").read_text(encoding="utf-8"))

# ── 2) 列表 ───────────────────────────────────────────
rows = s02_refs.list_pieces(refroot)
check("R5 列表带标题与存在性",
      len(rows) == 2 and all(r["exists"] for r in rows)
      and {r["title"] for r in rows} == {"甲", "乙"}, str(rows))

# ── 3) 校准 ───────────────────────────────────────────
res = s02_refs.calibrate(root=refroot, today="20260101", out_dir=tmp / "out")
check("R6 校准有阈值", res["label"]["density_high"] > res["label"]["density_low"],
      str(res["label"]))
check("R7 版本化文件写出", _Path(res["versioned"]).exists()
      and "20260101-002" in res["versioned"], res["versioned"])
check("R8 latest 与版本文件一致",
      _Path(res["latest"]).read_text(encoding="utf-8")
      == _Path(res["versioned"]).read_text(encoding="utf-8"))
check("R9 留一法有记录", len(res["loo"]) == 2 and "density" in res["loo_max_drift"],
      str(res["loo"]))
check("R10 有明确判断", res["verdict"] in ("样本基本够（漂移 ≤20%）",
                                           "样本不足（漂移 >20%，继续积累）"),
      res["verdict"])
log = _Path(res["log"]).read_text(encoding="utf-8")
check("R11 日志有表头与数据行", "校准日志" in log and "| 20260101 |" in log, log[-200:])
check("R12 对比报告写出", _Path(res["report"]).exists(), res["report"])

# ── 4) 再校准一次：版本号递增、日志追加 ────────────────
res2 = s02_refs.calibrate(root=refroot, today="20260101", out_dir=tmp / "out")
log2 = _Path(res2["log"]).read_text(encoding="utf-8")
check("R13 重复校准同一天同版本号（覆盖）", "20260101-002" in res2["versioned"])
check("R14 日志追加而非重写", log2.count("| 20260101 |") == 2, str(log2.count("| 20260101 |")))

# ── 5) 空库报错 ───────────────────────────────────────
empty = tmp / "empty"
empty.mkdir()
try:
    s02_refs.calibrate(root=empty, today="20260101")
except ValueError as e:
    check("R15 空库给出明确报错", "还没有登记" in str(e), str(e))
else:
    check("R15 空库给出明确报错", False, "没有抛错")

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
