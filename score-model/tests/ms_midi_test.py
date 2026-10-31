# -*- coding: utf-8 -*-
"""MIDI 导出 / 回读测试（III-1 / III-2）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_midi as mm
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def doc1():
    return ev.MSDocument(events=[
        ev.Event(id="a", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
                 release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
        ev.Event(id="b", instrument_id=1, onset_us=500_000, pitch=pitch(64), release_us=1_000_000,
                 release_state="given",
                 dynamics=ev.Dynamics(ms.VALUE, 1250, "relative_permille", "cal", "measured")),
    ], pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)])


TB = 500_000        # ♩=120
data, report = mm.write_midi(doc1(), time_base_us=TB)

# ── 头部 ────────────────────────────────────────────────────
check("M1 是 SMF（MThd）", data[:4] == b"MThd")
check("M2 format=1 / ntrks=1 / ppq=480",
      int.from_bytes(data[8:10], "big") == 1 and int.from_bytes(data[10:12], "big") == 1
      and int.from_bytes(data[12:14], "big") == 480)

# ── 换算 ────────────────────────────────────────────────────
check("M3 500ms ↔ 480 tick（♩=120, ppq=480）", mm.us_to_tick(500_000, TB) == 480,
      str(mm.us_to_tick(500_000, TB)))
check("M4 1000ms ↔ 960 tick", mm.us_to_tick(1_000_000, TB) == 960)
check("M5 250ms ↔ 240 tick", mm.us_to_tick(250_000, TB) == 240)

# ── velocity 映射（1000‰ ↔ 64） ───────────────────────────
check("M6 1000‰ → 64", mm.velocity_of(1000) == 64)
check("M7 1250‰ → 80", mm.velocity_of(1250) == 80, str(mm.velocity_of(1250)))
check("M8 极小值夹到 1", mm.velocity_of(1) == 1)
check("M9 极大值夹到 127", mm.velocity_of(100000) == 127)

# ── 踏板值 ─────────────────────────────────────────────────
check("M10 深度 1000 → 127", mm.pedal_value(1000) == 127)
check("M11 深度 500 → 64", mm.pedal_value(500) == 64, str(mm.pedal_value(500)))

# ── 回读一致 ───────────────────────────────────────────────
back = mm.read_midi(data)
check("M12 tempo meta = time_base", back["tempo_us"] == TB, str(back["tempo_us"]))
check("M13 音符事件 4 条（2 音 × on/off）", len(back["notes"]) == 4, str(len(back["notes"])))
ons = [n for n in back["notes"] if n["on"]]
offs = [n for n in back["notes"] if not n["on"]]
check("M14 两个 note-on 在 0 与 480 tick",
      sorted(n["tick"] for n in ons) == [0, 480], str([n["tick"] for n in ons]))
check("M15 力度 64 与 80",
      sorted(n["vel"] for n in ons) == [64, 80], str(sorted(n["vel"] for n in ons)))
check("M16 音高 60 与 64",
      sorted(n["note"] for n in ons) == [60, 64])
check("M17 note-off 时间 480 与 960",
      sorted(n["tick"] for n in offs) == [480, 960], str([n["tick"] for n in offs]))
check("M18 踏板 CC64：0→127 与 960→0",
      [c for c in back["ccs"] if c["cc"] == 64] ==
      [{"tick": 0, "ch": 0, "cc": 64, "val": 127},
       {"tick": 960, "ch": 0, "cc": 64, "val": 0}],
      str([c for c in back["ccs"] if c["cc"] == 64]))

# ── sustaining：note-off 落在末尾并记录 ────────────────────
d2 = ev.MSDocument(events=[
    ev.Event(id="s", instrument_id=1, onset_us=0, pitch=pitch(72), release_us=None,
             release_state="sustaining", dynamics=ev.Dynamics(ms.NOT_PROVIDED)),
    ev.Event(id="x", instrument_id=1, onset_us=1_000_000, pitch=pitch(60), release_us=1_500_000,
             release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
])
data2, rep2 = mm.write_midi(d2, time_base_us=TB)
back2 = mm.read_midi(data2)
check("M19 sustaining 的 note-off 记入报告", any(r["id"] == "s" for r in rep2["sustaining_note_offs"]),
      str(rep2["sustaining_note_offs"]))
check("M20 NOT_PROVIDED 力度记入报告且用锚点 64",
      "s" in rep2["not_provided_dynamics"] and
      any(n["on"] and n["note"] == 72 and n["vel"] == 64 for n in back2["notes"]))

# ── CC66 / CC67 独立断言（此前只有映射代码，无测试） ──────
d_ped = ev.MSDocument(events=[
    ev.Event(id="q", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
             release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
], pedals=[ev.PedalSegment(1, "sostenuto", 0, 500_000, 1000),
           ev.PedalSegment(1, "una_corda", 0, 500_000, 500)])
data_p, _ = mm.write_midi(d_ped, time_base_us=TB)
back_p = mm.read_midi(data_p)
ccs = {(c["cc"], c["val"]) for c in back_p["ccs"]}
check("M24 CC66 sostenuto 深度 1000 → 127", (66, 127) in ccs, str(sorted(ccs)))
check("M25 CC67 una_corda 深度 500 → 64", (67, 64) in ccs, str(sorted(ccs)))

# ── 演奏收束：结构合法但弹不出来的数据要报出来 ────────────
dup = ev.MSDocument(events=[
    ev.Event(id="x1", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
             release_state="given", dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured")),
    ev.Event(id="x2", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
             release_state="given", dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured")),
])
check("M26 结构校验放行同键同刻", ev.validate(dup) == [], str(ev.validate(dup)))
data_d, rep_d = mm.write_midi(dup, time_base_us=500_000)
check("M27 导出报告含 R-1 违规", any("R-1" in v for v in rep_d["realization"]),
      str(rep_d["realization"]))
try:
    mm.write_midi(dup, time_base_us=500_000, strict=True)
    check("M28 strict=True 时拒绝导出", False)
except ValueError as e:
    check("M28 strict=True 时拒绝导出", "演奏收束" in str(e), str(e)[:40])

# ── 多琴 → 不同通道 ────────────────────────────────────────
d3 = ev.MSDocument(piano_count=2, constraint_mode="n_pianos", events=[
    ev.Event(id="p1", instrument_id=1, onset_us=0, pitch=pitch(60), release_us=500_000,
             release_state="given", dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured")),
    ev.Event(id="p2", instrument_id=2, onset_us=0, pitch=pitch(60), release_us=500_000,
             release_state="given", dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured")),
])
data3, _ = mm.write_midi(d3, time_base_us=TB)
back3 = mm.read_midi(data3)
check("M21 两琴分到不同通道",
      sorted({n["ch"] for n in back3["notes"] if n["on"]}) == [0, 1],
      str(sorted({n["ch"] for n in back3["notes"] if n["on"]})))

# ── 参数校验 ───────────────────────────────────────────────
try:
    mm.write_midi(doc1(), time_base_us=0)
except ValueError:
    check("M22 time_base ≤0 → 拒绝", True)
else:
    check("M22 time_base ≤0 → 拒绝", False)

# ── 确定性（同一输入同字节） ───────────────────────────────
check("M23 导出确定性", mm.write_midi(doc1(), time_base_us=TB)[0] == data)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
