# -*- coding: utf-8 -*-
"""V-3 欠账清理后的行为测试：gaps 结构 + grace 退化上报。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_author as au
import ms_events as ev
import ms_io as mj
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


# ── gaps 结构（欠账①） ────────────────────────────────────
d = ev.MSDocument(events=[])
d.gaps.append({"code": "not_modelled", "where": "direction-type/octave-shift",
               "detail": "未建模元素", "severity": "info"})
text = mj.dumps(d)
check("G1 合法 gap 可写出", "not_modelled" in text)
back = mj.loads(text)
check("G2 合法 gap 可读回", back.gaps[0]["code"] == "not_modelled")

d2 = ev.MSDocument(events=[])
d2.gaps.append({"reason": "缺 code"})
try:
    mj.dumps(d2)
except ValueError as e:
    check("G3 缺 code 的 gap → 拒绝写出", True, str(e)[:40])
else:
    check("G3 缺 code 的 gap → 拒绝写出", False, "应当拒绝")

d3 = ev.MSDocument(events=[])
d3.gaps.append({"code": "x", "severity": "fatal"})
try:
    mj.dumps(d3)
except ValueError:
    check("G4 非法 severity → 拒绝", True)
else:
    check("G4 非法 severity → 拒绝", False)

d4 = ev.MSDocument(events=[])
d4.gaps.append({"code": "x", "unknown_field": 1})
try:
    mj.dumps(d4)
except ValueError:
    check("G5 未知字段 → 拒绝", True)
else:
    check("G5 未知字段 → 拒绝", False)

raw = mj.dumps(ev.MSDocument(events=[]))
bad = raw.replace("gaps 0", "gaps 1\nnocode bad 非法 severity", 1)
try:
    mj.loads(bad)
except ValueError:
    check("G6 读入侧同样校验 gap", True)
else:
    check("G6 读入侧同样校验 gap", False)

# ── grace 退化上报（欠账④） ───────────────────────────────
w = []
evs = au.write_note(onset_us=0, duration_us=400_000, semitone=60,
                    ornament="grace_short", warnings=w)
check("G7 无空间时退化为拍上并上报",
      len(evs) == 2 and any(x["code"] == "grace_onbeat" for x in w), str(w))
check("G8 退化后两音不同起点（不再同时起音）", evs[0].onset_us == 0 and evs[1].onset_us > 0,
      f"{evs[0].onset_us},{evs[1].onset_us}")

w2 = []
evs2 = au.write_note(onset_us=1_000_000, duration_us=400_000, semitone=60,
                     ornament="grace_short", warnings=w2)
check("G9 有空间时拍前，不产生警告", w2 == [] and evs2[0].onset_us < evs2[1].onset_us, str(w2))

# ── 不传 warnings 也不报错（向后兼容） ────────────────────
evs3 = au.write_note(onset_us=0, duration_us=400_000, semitone=60, ornament="grace_short")
check("G10 不传 warnings 仍可用", len(evs3) == 2)

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
