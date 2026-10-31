# -*- coding: utf-8 -*-
"""渲染器接入演奏收束检查（SM0142）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_render as rd
import ms_render_jianpu as jp
import ms_render as ro
import ms_render_staff2 as st
import ms_score as sc
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi=60):
    return ev.Pitch("C", 0, 4, semi)


def dup_doc():
    e = dict(instrument_id=1, onset_us=0, pitch=pitch(), release_us=500_000,
             release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured"))
    return ev.MSDocument(events=[ev.Event(id="a", **e), ev.Event(id="b", **e)])


O = ro.RenderOptions(meter=(4, 4), time_base_us=500_000)

CASES = [
    ("pianoroll", lambda d, w: rd.render_pianoroll(d, options=O, warnings=w)),
    ("staff", lambda d, w: rd.render_staff(d, options=O, warnings=w)),
    ("staff2", lambda d, w: st.render_staff2(d, O, warnings=w)),
    ("jianpu", lambda d, w: jp.render_jianpu(d, O, warnings=w)),
    ("score", lambda d, w: sc.render_score(d, O, warnings=w)),
]

for name, fn in CASES:
    w = []
    svg = fn(dup_doc(), w)
    check(f"RZ-{name} 报出演奏收束问题", any("R-1" in x for x in w), str(w[:1]))
    check(f"RZ-{name} 仍正常产图", svg.startswith("<svg"), svg[:20])

for name, fn in CASES:
    w = []
    fn(ev.MSDocument(events=[ev.Event(id="ok", instrument_id=1, onset_us=0, pitch=pitch(),
                                      release_us=500_000, release_state="given")]), w)
    check(f"RZ-{name} 干净数据不误报", w == [], str(w[:1]))

# 不传 warnings 时行为不变（向后兼容）
check("RZ-向后兼容：不传 warnings 不报错",
      rd.render_pianoroll(dup_doc(), options=O).startswith("<svg"))

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
