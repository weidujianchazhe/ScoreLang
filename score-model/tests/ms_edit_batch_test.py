# -*- coding: utf-8 -*-
"""批量编辑测试（IV-2）：移调 / 量化 / 批量力度。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_dynamics_levels as dl
import ms_edit as ed
import ms_events as ev
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(step, alter, octv, semi):
    return ev.Pitch(step, alter, octv, semi)


def doc():
    return ev.MSDocument(events=[
        ev.Event(id="a", instrument_id=1, onset_us=0, pitch=pitch("C", 0, 4, 60),
                 release_us=500_000, release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
        ev.Event(id="b", instrument_id=1, onset_us=123_000, pitch=pitch("E", -1, 4, 63),
                 release_us=623_000, release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1200, "relative_permille", "cal", "measured")),
    ])


# ── 移调 ────────────────────────────────────────────────────
r = ed.transpose(doc(), 2)
check("T1 移调成功", r.ok, str(r.errors))
check("T2 C4→D4、E♭4→F4（半音 +2）",
      [e.pitch.semitone for e in r.doc.events] == [62, 65], str([e.pitch.semitone for e in r.doc.events]))
check("T3 拼写重新规范化且自洽",
      all(e.pitch.consistent() for e in r.doc.events), str([e.pitch for e in r.doc.events]))
check("T4 时间不变", [e.onset_us for e in r.doc.events] == [0, 123_000])
check("T5 结果合法", ev.validate(r.doc) == [], str(ev.validate(r.doc)))

check("T6 移调 0 半音 = 原样（半音）", [e.pitch.semitone for e in ed.transpose(doc(), 0).doc.events] == [60, 63])

r_bad = ed.transpose(doc(), 100)
check("T7 越界移调被拒", (not r_bad.ok) and "越界" in r_bad.errors[0], str(r_bad.errors))
check("T8 失败不修改原文档", len(doc().events) == 2)

# ── 量化 ────────────────────────────────────────────────────
q = ed.quantize(doc(), 100_000)
check("Q1 量化成功", q.ok, str(q.errors))
check("Q2 起点 123ms → 100ms", q.doc.events[1].onset_us == 100_000, str(q.doc.events[1].onset_us))
check("Q3 终点 623ms → 600ms", q.doc.events[1].release_us == 600_000, str(q.doc.events[1].release_us))
check("Q4 整数起点不变", q.doc.events[0].onset_us == 0)
check("Q5 结果合法", ev.validate(q.doc) == [], str(ev.validate(q.doc)))

# 吸附后终点 ≤ 起点 → 顺延一格
tight = ev.MSDocument(events=[
    ev.Event(id="x", instrument_id=1, onset_us=140_000, pitch=pitch("C", 0, 4, 60),
             release_us=160_000, release_state="given")])
qt = ed.quantize(tight, 100_000)
check("Q6 终点点被吸附到同点 → 顺延一格", qt.ok and qt.doc.events[0].release_us > qt.doc.events[0].onset_us,
      f"{qt.doc.events[0].onset_us}..{qt.doc.events[0].release_us}")

q_bad = ed.quantize(doc(), 0)
check("Q7 grid ≤0 被拒", not q_bad.ok)

# ── 批量力度 ────────────────────────────────────────────────
d = ed.set_all_dynamics(doc(), level="mf")
check("D1 批量等级成功", d.ok, str(d.errors))
check("D2 全部变为 1250", all(e.dynamics.permille == 1250 for e in d.doc.events))
check("D3 来源 notated_inferred + 等级表版本",
      all(e.dynamics.src == "notated_inferred" and e.dynamics.calibration_ref == dl.LEVELS_VERSION
          for e in d.doc.events))

d2 = ed.set_all_dynamics(doc(), permille=900)
check("D4 批量数值成功（src=None 表示直接给值）",
      d2.ok and all(e.dynamics.permille == 900 and e.dynamics.src is None for e in d2.doc.events))

check("D5 同时给等级与数值 → 拒", not ed.set_all_dynamics(doc(), level="mf", permille=900).ok)
check("D6 都不给 → 拒", not ed.set_all_dynamics(doc()).ok)
check("D7 非法等级 → 拒", not ed.set_all_dynamics(doc(), level="sfz").ok)

# ── 组合：移调 + 量化 + 力度，仍合法 ──────────────────────
s1 = ed.transpose(doc(), -2)
s2 = ed.quantize(s1.doc, 50_000)
s3 = ed.set_all_dynamics(s2.doc, level="p")
check("C1 组合编辑全部成功", s1.ok and s2.ok and s3.ok, f"{s1.errors}{s2.errors}{s3.errors}")
check("C2 组合结果合法", ev.validate(s3.doc) == [], str(ev.validate(s3.doc)))
check("C3 组合保留移调结果", [e.pitch.semitone for e in s3.doc.events] == [58, 61])

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
