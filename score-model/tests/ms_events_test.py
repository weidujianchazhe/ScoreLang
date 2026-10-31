# -*- coding: utf-8 -*-
"""卡 A 验收测试：MS 事件容器 + SPEC §7.7 六条不变量。

负例设计原则（卡 A 要点⑤）：每条不变量都必须先能构造出违反它的对象，
再证明新实现拒绝。旧实现（ms_fields 字段表）**没有这些概念**——
本文件同时证明这一点（结构性缺失，而不是"规则偏松"）。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_semantics as ms

OK, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def base_event(**kw):
    d = dict(
        id="e1", instrument_id=1, onset_us=1_000_000,
        pitch=ev.Pitch("C", 0, 4, 60),
        excitation_type="impulse",
        release_us=1_500_000, release_state="given",
        dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "steinway-b;v1", "measured"),
    )
    d.update(kw)
    return ev.Event(**d)


# ── 正例 ─────────────────────────────────────────────────────
doc = ev.MSDocument(piano_count=1, events=[
    base_event(),
    base_event(id="e2", onset_us=2_000_000, release_us=2_400_000),
])
check("P1 合法文档无错", ev.validate(doc) == [], str(ev.validate(doc)))

# ── 负例：V1 释放三态 ────────────────────────────────────────
d = ev.MSDocument(events=[base_event(release_state="sustaining", release_us=1_500_000)])
check("N1 sustaining 却带 release_us → 拒绝", any("V1" in e for e in ev.validate(d)), str(ev.validate(d)))

d = ev.MSDocument(events=[base_event(release_state="given", release_us=None)])
check("N2 given 却无 release_us → 拒绝", any("V1" in e for e in ev.validate(d)))

# ── 负例：V2 释放与起始 ──────────────────────────────────────
d = ev.MSDocument(events=[base_event(onset_us=2_000_000, release_us=1_000_000)])
check("N3 时间倒流 → 拒绝", any("V2" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(release_us=1_000_000)])
check("N4 零时长非 grace → 拒绝", any("V2" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(release_us=1_000_000, is_grace=True)])
check("P2 零时长 + grace → 允许", ev.validate(d) == [], str(ev.validate(d)))

# ── 负例：V3 力度 ────────────────────────────────────────────
d = ev.MSDocument(events=[base_event(dynamics=ev.Dynamics(ms.VALUE, 0, "relative_permille", "c", "measured"))])
check("N5 力度=0（无音符语义）→ 拒绝", any("V3" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(dynamics=ev.Dynamics(ms.NOT_PROVIDED, 1000))])
check("N6 NOT_PROVIDED 却填 1000 → 拒绝（缺失≠中性）", any("V3" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", None, "measured"))])
check("N7 缺 calibration_ref → 拒绝", any("V3" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "handmade"))])
check("N8 伪造来源 → 拒绝", any("V3" in e for e in ev.validate(d)))

# ── 负例：V5 音高与钢琴 ──────────────────────────────────────
d = ev.MSDocument(events=[base_event(pitch=ev.Pitch("C", 0, 9, 120))])
errs = ev.validate(d)
check("N9 音高越界 → UNSUPPORTED_PITCH_RANGE", any(ev.ERR_PITCH_RANGE in e for e in errs), str(errs))

d = ev.MSDocument(events=[base_event(pitch=ev.Pitch("D", 0, 4, 60))])
check("N10 拼写与半音不一致 → 拒绝", any("拼写" in e for e in ev.validate(d)))

d = ev.MSDocument(events=[base_event(instrument_id=2)])
check("N11 instrument_id 超出 piano_count → 拒绝", any("V5" in e for e in ev.validate(d)))

# ── 负例：V4 踏板 ────────────────────────────────────────────
seg = ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)
d = ev.MSDocument(pedals=[seg, ev.PedalSegment(1, "sustain", 500_000, 1_500_000, 1000)])
check("N12 同琴同踏板段重叠 → 拒绝", any("V4" in e for e in ev.validate(d)))

d = ev.MSDocument(pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1001)])
check("N13 踏板深度越界 → 拒绝", any("V4" in e for e in ev.validate(d)))

d = ev.MSDocument(pedals=[ev.PedalSegment(1, "sostenuto", 0, 1_000_000, 1000, "explicit")])
check("N14 explicit 无 targets → 拒绝", any("V4" in e for e in ev.validate(d)))

d = ev.MSDocument(pedals=[ev.PedalSegment(1, "sostenuto", 0, 1_000_000, 1000, "mechanical", ("global",))])
check("N15 mechanical 带 targets → 拒绝", any("V4" in e for e in ev.validate(d)))

d = ev.MSDocument(constraint_mode="unlimited", pedals=[ev.PedalSegment(1, "sustain", 0, 1, 1000, "mechanical")])
check("N16 unlimited 下 mechanical → 拒绝", any("V6" in e for e in ev.validate(d)))

# ── 结构 vs 演奏收束：同键同 onset 在结构上合法，只有落到琴上才非法 ──
d = ev.MSDocument(events=[base_event(), base_event(id="e2")])
check("N17 同键同 onset 结构上合法（不再由 validate 拒绝）",
      ev.validate(d) == [], str(ev.validate(d)))
check("N17b 同键同 onset 在演奏收束时报 R-1",
      any("R-1" in e for e in ev.check_realization(d)), str(ev.check_realization(d)))

d = ev.MSDocument(constraint_mode="unlimited", events=[base_event(), base_event(id="e2")])
check("P3 unlimited 下允许同键同 onset", ev.validate(d) == [], str(ev.validate(d)))

# 旧实现对照（L1/L2）已随旧字段表一起退役（2026-10-19）：字段表被删除，
# 其"缺乏事件概念"的结论已由 SM0063 记录在案，不再在此重复依据。

# ── 输出 ─────────────────────────────────────────────────────
bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[{FAIL}] {name}  {detail}")
print(f"{'='*50}")
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
