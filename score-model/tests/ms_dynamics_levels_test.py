# -*- coding: utf-8 -*-
"""写谱层默认力度等级表测试（`dyn-levels-v1`）+ 与计算层的隔离。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_audio as au
import ms_dynamics_levels as dl
import ms_edit as ed
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def base():
    return ev.MSDocument(events=[
        ev.Event(id="e1", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
                 release_us=500_000, release_state="given",
                 dynamics=ev.Dynamics(ms.NOT_PROVIDED)),
    ])


# ── 表本身 ───────────────────────────────────────────────────
check("L1 锚点 mp = 1000", dl.level_to_permille("mp") == 1000, str(dl.level_to_permille("mp")))
check("L2 mf = 1250", dl.level_to_permille("mf") == 1250)
check("L3 ff = 1750", dl.level_to_permille("ff") == 1750)
check("L4 ppp = 250", dl.level_to_permille("ppp") == 250)
check("L5 全部在合法区间 [1,100000]",
      all(1 <= v <= 100000 for v in dl.PERMILLE.values()), str(dl.PERMILLE))
check("L6 等级单调（越强越大）",
      dl.PERMILLE["ppp"] < dl.PERMILLE["pp"] < dl.PERMILLE["p"] < dl.PERMILLE["mp"]
      < dl.PERMILLE["mf"] < dl.PERMILLE["f"] < dl.PERMILLE["ff"] < dl.PERMILLE["fff"])
check("L7 版本号存在", dl.LEVELS_VERSION == "dyn-levels-v1")

try:
    dl.level_to_permille("sfz")
except KeyError:
    check("L8 未知等级拒绝", True)
else:
    check("L8 未知等级拒绝", False, "应当 KeyError")

name, dist = dl.permille_to_nearest_level(1240)
check("L9 反查回显（mf 最近）", name == "mf" and dist == 10, f"{name}/{dist}")

# ── 写谱 → MS ────────────────────────────────────────────────
d = base()
r = ed.set_dynamics_level(d, "e1", "mf")
check("L10 选 mf → 写入数值 1250", r.ok and r.doc.events[0].dynamics.permille == 1250, str(r.errors))
check("L11 来源标 notated_inferred", r.doc.events[0].dynamics.src == "notated_inferred")
check("L12 标定引用记等级表版本", r.doc.events[0].dynamics.calibration_ref == "dyn-levels-v1")

r2 = ed.set_dynamics_level(d, "e1", "sfz")
check("L13 未知等级 → 拒绝且不改文档", (not r2.ok) and r2.doc is d)

# ── 关键：等级不进入 MS 语义（P3） ──────────────────────────
text_shape = r.doc.events[0]
check("L14 MS 里没有'等级'字段", not hasattr(text_shape, "level"))

# ── 关键：计算层只吃数值（P2） ──────────────────────────────
d_a = base()
d_a.events[0] = ev.Event(id="e1", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
                         release_us=500_000, release_state="given",
                         dynamics=ev.Dynamics(ms.VALUE, 1250, "relative_permille", "x", "notated_inferred"))
d_b = base()
d_b.events[0] = ev.Event(id="e1", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
                         release_us=500_000, release_state="given",
                         dynamics=ev.Dynamics(ms.VALUE, 1250, "relative_permille", "y", "measured"))
pa = au.event_parameters(d_a)[0]
pb = au.event_parameters(d_b)[0]
check("L15 同数值不同来源 → 计算输出一致（计算只看数值）",
      abs(pa["amplitude"] - pb["amplitude"]) < 1e-12,
      f"{pa['amplitude']} vs {pb['amplitude']}")

# ── 未给等级时不得自动填 ────────────────────────────────────
d_c = base()
check("L16 未给等级保持 NOT_PROVIDED", d_c.events[0].dynamics.state == ms.NOT_PROVIDED)
params = au.event_parameters(d_c)[0]
check("L17 计算按中性但留痕",
      abs(params["amplitude"] - 1.0) < 1e-12 and params["dynamics_state"] == ms.NOT_PROVIDED
      and params["dynamics_permille"] is None)

# ── 换表不改兼容（存数值不存等级） ──────────────────────────
check("L18 文档里存的是数值，换表不影响已写数据",
      r.doc.events[0].dynamics.permille == 1250
      and not hasattr(r.doc.events[0].dynamics, "level"))

bad = [x for x in results if not x[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
