# -*- coding: utf-8 -*-
"""P1 验证：结构允许的东西，计算层不得拒绝、不得合并、不得报错。

管理者原话（2026-10-19）："数学结构上允许这种情况的发生…在写谱的时候会进行收束…
允许后，它也同样可以计算。"

对应三条断言：
  A. 数学结构：`unlimited` 下同键同刻多事件、多琴、踏板重叠 —— **通过校验**
  B. 计算层：这些事件**各自出参数**（不合并、不因物理不可能报错）
  C. 写谱层：切回 `single_piano` 后同一份数据**被拒绝**（收束生效）
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re

import ms_audio as au
import ms_events as ev
import ms_render as rd
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def dup_doc(mode="unlimited", count=1):
    """同一键同一时刻 3 个事件（物理不可能，结构允许）。"""
    dyn = ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")
    return ev.MSDocument(piano_count=count, constraint_mode=mode, events=[
        ev.Event(id=f"d{i}", instrument_id=1, onset_us=1_000_000, pitch=ev.Pitch("C", 0, 4, 60),
                 release_us=1_500_000, release_state="given", dynamics=dyn)
        for i in range(3)
    ])


# ── A. 结构允许 ─────────────────────────────────────────────
d = dup_doc()
check("P1-A1 unlimited 下同键同刻 ×3 → 校验通过", ev.validate(d) == [], str(ev.validate(d)))

d2 = ev.MSDocument(constraint_mode="unlimited", pedals=[
    ev.PedalSegment(1, "sustain", 0, 1_000_000, 500, "explicit", ("global",)),
    ev.PedalSegment(1, "sustain", 200_000, 800_000, 1000, "explicit", ("global",)),
])
check("P1-A2 unlimited 下同踏板段重叠 → 校验通过", ev.validate(d2) == [], str(ev.validate(d2)))

# ── B. 允许后仍可计算（核心） ───────────────────────────────
params = au.event_parameters(d)
check("P1-B1 同键同刻 ×3 各出一条参数（不合并）", len(params) == 3, str(len(params)))
check("P1-B2 频率一致（同一个键）",
      len({p["freq_hz"] for p in params}) == 1, str({p["freq_hz"] for p in params}))
# 计算层不得因"物理不可能"拒绝或静默合并：真跑一遍，失败即红（原为恒真占位，已修）
try:
    _p_dup = au.event_parameters(d)
    _calc_ok = (len(_p_dup) == 3) and all(p["dynamics_state"] == "VALUE" for p in _p_dup)
except Exception:  # noqa: BLE001
    _calc_ok = False
check("P1-B3 计算未因'物理不可能'报错且未合并", _calc_ok, "参数条数应仍为 3")

# 同刻同键但力度不同 → 参数各自保留差异
d3 = dup_doc()
d3.events[0] = ev.Event(id="d0", instrument_id=1, onset_us=1_000_000, pitch=ev.Pitch("C", 0, 4, 60),
                        release_us=1_500_000, release_state="given",
                        dynamics=ev.Dynamics(ms.VALUE, 500, "relative_permille", "cal", "measured"))
p3 = au.event_parameters(d3)
check("P1-B4 力度差异被保留（未被合并平均）",
      p3[0]["amplitude"] != p3[2]["amplitude"], f"{p3[0]['amplitude']} vs {p3[2]['amplitude']}")

# 渲染也能画（不塌缩成一个图元）
svg = rd.render_pianoroll(d)
check("P1-B5 渲染出 3 个事件图元（不塌缩）",
      len(re.findall(r'class="note"', svg)) == 3, str(len(re.findall(r'class="note"', svg))))

# 踏板重叠也能被计算消费
tracks = au.pedal_track_parameters(d2)
check("P1-B6 重叠踏板段都进了参数（不丢段）",
      len(tracks["1:sustain"]) == 2, str(tracks))

# ── B'. 多琴：允许各琴同刻同键 ──────────────────────────────
multi = ev.MSDocument(piano_count=2, constraint_mode="n_pianos", events=[
    ev.Event(id="a", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
             release_us=500_000, release_state="given"),
    ev.Event(id="b", instrument_id=2, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
             release_us=500_000, release_state="given"),
])
check("P1-B7 两琴同刻同键 → 通过且可算", ev.validate(multi) == [] and len(au.event_parameters(multi)) == 2)

# ── C. 写谱层收束 ───────────────────────────────────────────
d4 = dup_doc(mode="single_piano")
check("P1-C1 同一份数据在结构层仍合法，收束层报 R-1",
      ev.validate(d4) == [] and any("R-1" in e for e in ev.check_realization(d4)),
      str(ev.check_realization(d4)))

d5 = ev.MSDocument(constraint_mode="single_piano", pedals=[
    ev.PedalSegment(1, "sustain", 0, 1_000_000, 500),
    ev.PedalSegment(1, "sustain", 200_000, 800_000, 1000),
])
check("P1-C2 同踏板重叠在 single_piano 下被拒绝",
      any("V4" in e for e in ev.validate(d5)))

d6 = ev.MSDocument(piano_count=2, constraint_mode="n_pianos", events=[
    ev.Event(id="a", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
             release_us=500_000, release_state="given"),
    ev.Event(id="b", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
             release_us=500_000, release_state="given"),
])
check("P1-C3 同一台琴同刻同键（n_pianos）→ 收束层报 R-1", any("R-1" in e for e in ev.check_realization(d6)))

# ── 音高域：唯一不因"允许"而放开的东西 ─────────────────────
d7 = dup_doc()
d7.events[0] = ev.Event(id="d0", instrument_id=1, onset_us=1_000_000, pitch=ev.Pitch("C", 0, 9, 120),
                        release_us=1_500_000, release_state="given")
check("P1-D1 即使 unlimited，越界音高仍拒绝（可计算性边界）",
      any(ev.ERR_PITCH_RANGE in e for e in ev.validate(d7)), str(ev.validate(d7)))

bad = [x for x in results if not x[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
