# -*- coding: utf-8 -*-
"""控制曲线测试：起点/转折/渐进 + 校验 + 渲染插值。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import make_audio
import ms_events as ev
import ms_io
import ms_semantics as ms
import ms_validate

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def one_inst():
    return [ev.Instrument("P1", "acoustic_grand_piano")]


def doc(curves=(), permille=300):
    e = ev.Event(id="L00000001", instrument_id=1, onset_us=0, release_us=1_000_000,
                 pitch=ev.Pitch("C", 0, 4, 60), release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, permille, "relative_permille", "c", "measured"))
    return ev.MSDocument(events=[e], instruments=one_inst(), curves=list(curves))


# 1) 往返
d1 = doc([ev.CurvePoint(1, "dynamics", 0, 300, 0), ev.CurvePoint(1, "dynamics", 1_000_000, 1000, 1)])
back = ms_io.parse(ms_io.dump(d1))
check("K1 曲线往返", [(c.param, c.time_us, c.value, c.ramp) for c in back.curves]
      == [("dynamics", 0, 300, 0), ("dynamics", 1_000_000, 1000, 1)], str(back.curves))

# 2) 首点必须阶跃
bad1 = doc([ev.CurvePoint(1, "dynamics", 0, 300, 1)])
check("K2 首点 ramp=1 → 拒绝",
      any("V15" in e and "首点" in e for e in ms_validate.validate(bad1)),
      str(ms_validate.validate(bad1)))

# 3) 时间必须递增
bad2 = doc([ev.CurvePoint(1, "dynamics", 0, 300, 0), ev.CurvePoint(1, "dynamics", 0, 800, 1)])
check("K3 时间不递增 → 拒绝",
      any("V15" in e and "递增" in e for e in ms_validate.validate(bad2)),
      str(ms_validate.validate(bad2)))

# 4) 渲染：渐强让后段能量上升
def ratio(x):
    m = x.mean(axis=1)
    late = float(np.sqrt((m[int(0.6 * 44100):int(0.9 * 44100)] ** 2).mean()))
    early = float(np.sqrt((m[int(0.05 * 44100):int(0.2 * 44100)] ** 2).mean()))
    return late / max(1e-9, early)


flat = ratio(make_audio.render(doc()))
ramp = ratio(make_audio.render(d1))
check("K4 渐强提升后段能量", ramp > flat * 1.3, f"{ramp:.2f} vs {flat:.2f}")

# 5) 没有曲线 = 行为不变
same = np.allclose(make_audio.render(doc()), make_audio.render(doc(curves=[])))
check("K5 无曲线时渲染一致", bool(same))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
