# -*- coding: utf-8 -*-
"""`articulation-v1` 测试：取值来自 MuseScore 实现，行为必须与表一致。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_articulation as art
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# ── 表值与出处 ───────────────────────────────────────────────
check("A1 staccato 时长 50%", art.gate_pm("staccato") == 500)
check("A2 staccatissimo 33%", art.gate_pm("staccatissimo") == 330)
check("A3 tenuto 100%", art.gate_pm("tenuto") == 1000)
check("A4 marcato 67% + 力度 120%",
      art.gate_pm("marcato") == 670 and art.vel_pm("marcato") == 1200)
check("A5 accent 力度 120% 且不改时长",
      art.vel_pm("accent") == 1200 and art.gate_pm("accent") == 1000)
check("A6 版本号", art.VERSION == "articulation-v1")
check("A7 出处标注存在",
      "MuseScore" in art.ARTICULATIONS["staccato"]["src"], art.ARTICULATIONS["staccato"]["src"])

# ── 换算行为（整数微秒） ────────────────────────────────────
check("A8 staccato: 1_000_000µs → 500_000µs", art.apply_duration(1_000_000, "staccato") == 500_000)
check("A9 staccatissimo: 1_000_000 → 330_000", art.apply_duration(1_000_000, "staccatissimo") == 330_000)
check("A10 tenuto 不变", art.apply_duration(777_777, "tenuto") == 777_777)
check("A11 marcato: 1_000_000 → 670_000", art.apply_duration(1_000_000, "marcato") == 670_000)
check("A12 四舍五入（333µs × 50% = 167µs）", art.apply_duration(333, "staccato") == 167, str(art.apply_duration(333, "staccato")))

# ── 力度修正 ────────────────────────────────────────────────
check("A13 marcato 1250‰ → 1500‰", art.apply_dynamics(1250, "marcato") == 1500)
check("A14 staccato 不改力度", art.apply_dynamics(1250, "staccato") == 1250)
check("A15 未提供力度 → 仍为 None（不得被补成数值）",
      art.apply_dynamics(None, "marcato") is None)

# ── 组合 ────────────────────────────────────────────────────
d, p = art.apply(800_000, 1000, "marcato")
check("A16 组合换算", (d, p) == (536_000, 1200), f"{d},{p}")

# ── 未知奏法拒绝 ────────────────────────────────────────────
for fn in (art.gate_pm, art.vel_pm):
    try:
        fn("legato")
    except KeyError:
        check(f"A17-{fn.__name__} 未知奏法拒绝", True)
    else:
        check(f"A17-{fn.__name__} 未知奏法拒绝", False, "应当 KeyError")

# ── 与 MS 的一致性：换算结果可直接构造合法事件 ──────────────
d_us = art.apply_duration(1_000_000, "staccato")
pm = art.apply_dynamics(1000, "staccato")
e = ev.Event(id="x", instrument_id=1, onset_us=0,
             pitch=ev.Pitch("C", 0, 4, 60), release_us=d_us, release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, pm, "relative_permille", "dyn-levels-v1", "notated_inferred"))
doc = ev.MSDocument(events=[e])
check("A18 换算结果能构造合法 MS 乐谱模型", ev.validate(doc) == [], str(ev.validate(doc)))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
