# -*- coding: utf-8 -*-
"""呈现参数模型测试（II-1）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_render as ro

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def expect_error(name, **kw):
    try:
        ro.RenderOptions(**kw)
    except ValueError:
        check(name, True)
    else:
        check(name, False, "应当 ValueError")


# ── 默认值可用 ──────────────────────────────────────────────
d = ro.RenderOptions()
check("R1 默认可用", d.px_per_sec == 120.0 and d.clef == "treble")
check("R2 默认无小节语境", d.has_bar_context() is False and d.bar_duration_us() is None)
check("R3 无语境时小节起点为空（不猜）", d.bar_starts_us(5_000_000) == [])

# ── 小节语境 ────────────────────────────────────────────────
o44 = ro.RenderOptions(meter=(4, 4), time_base_us=500_000)   # ♩=120
check("R4 4/4 一小节 2s", o44.bar_duration_us() == 2_000_000, str(o44.bar_duration_us()))
check("R5 4/4 拍长 500ms", o44.beat_duration_us() == 500_000)
check("R6 5 秒内小节起点 = 0,2s,4s",
      o44.bar_starts_us(5_000_000) == [0, 2_000_000, 4_000_000], str(o44.bar_starts_us(5_000_000)))

o34 = ro.RenderOptions(meter=(3, 4), time_base_us=500_000)
check("R7 3/4 一小节 1.5s", o34.bar_duration_us() == 1_500_000, str(o34.bar_duration_us()))

o68 = ro.RenderOptions(meter=(6, 8), time_base_us=500_000)
# 6 个八分音符：每个 250ms → 1.5s
check("R8 6/8 一小节 1.5s", o68.bar_duration_us() == 1_500_000, str(o68.bar_duration_us()))
check("R9 6/8 拍长 250ms", o68.beat_duration_us() == 250_000)

# ── 只有 meter、没有 time_base → 仍不给小节（不猜） ────────
o_no_tb = ro.RenderOptions(meter=(4, 4))
check("R10 缺 time_base → 不画小节", o_no_tb.bar_duration_us() is None and o_no_tb.bar_starts_us(9_000_000) == [])

# ── 校验 ────────────────────────────────────────────────────
expect_error("R11 px_per_sec ≤0 → 拒绝", px_per_sec=0)
expect_error("R12 clef 非法 → 拒绝", clef="alto")
expect_error("R13 key_sig 越界 → 拒绝", key_sig=9)
expect_error("R14 meter.beats 非法 → 拒绝", meter=(0, 4))
expect_error("R15 meter.beat_type 非法 → 拒绝", meter=(4, 3))
expect_error("R16 meter 形态非法 → 拒绝", meter=(4,))
expect_error("R17 time_base ≤0 → 拒绝", time_base_us=0)
expect_error("R18 bars_per_line <1 → 拒绝", bars_per_line=0)

# ── 描述串标注"未指定" ─────────────────────────────────────
s = d.describe()
check("R19 缺语境时描述注明未指定", "未指定" in s, s)
s2 = o44.describe()
check("R20 有语境时描述含 meter/time_base",
      "meter=4/4" in s2 and "time_base=500000µs" in s2.replace("/♩", "µs"), s2)

# ── 序列化 ─────────────────────────────────────────────────
info = ro.as_dict(o44)
check("R21 as_dict 含派生字段",
      info["bar_duration_us"] == 2_000_000 and info["has_bar_context"] is True, str(info))

# ── 不可变 ─────────────────────────────────────────────────
try:
    o44.px_per_sec = 999
except Exception:
    check("R22 参数对象不可变", True)
else:
    check("R22 参数对象不可变", False, "应当不可写")

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
