# -*- coding: utf-8 -*-
"""收束按机制：可演奏性测试。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_playability as pl
import ms_semantics as ms

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
            5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
            10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def evt(iid, onset, semi, eid, dur=300_000):
    return ev.Event(id=eid, instrument_id=iid, onset_us=onset, release_us=onset + dur,
                    pitch=pitch(semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 700, "relative_permille", "c", "measured"))


def doc(inst, events):
    d = ev.MSDocument(events=list(events), instruments=list(inst))
    d.piano_count = len(inst)
    return d


# C1/C2：钢琴 14 音同刻、跨度 60 半音 → 两者都报警
many = [evt(1, 0, 36 + i, f"L{i:08d}") for i in range(14)]
d1 = doc([ev.Instrument("P1", "acoustic_grand_piano")], many)
r1 = pl.check_playability(d1)
check("C1 钢琴同刻超 10 音", any(x.startswith("C1") for x in r1), str(r1[:2]))
check("C2 和弦跨度超 12 度", any(x.startswith("C2") for x in r1), str(r1[:2]))

# C4：长笛（单音）重叠
d2 = doc([ev.Instrument("P1", "flute")], [evt(1, 0, 72, "L00000001"), evt(1, 100_000, 74, "L00000002")])
check("C4 单音乐器重叠", any(x.startswith("C4") for x in pl.check_playability(d2)), str(pl.check_playability(d2)))

# C6：小提琴三音同刻
d3 = doc([ev.Instrument("P1", "violin")],
         [evt(1, 0, 60, "L00000001"), evt(1, 0, 64, "L00000002"), evt(1, 0, 67, "L00000003")])
check("C6 弓弦超双音", any(x.startswith("C6") for x in pl.check_playability(d3)), str(pl.check_playability(d3)))

# 正常：钢琴 3 音和弦不报
d4 = doc([ev.Instrument("P1", "acoustic_grand_piano")],
         [evt(1, 0, 60, "L00000001"), evt(1, 0, 64, "L00000002"), evt(1, 0, 67, "L00000003")])
check("正常三和弦不报", pl.check_playability(d4) == [], str(pl.check_playability(d4)))

# 结构允许但收束报警：MS 写入不被阻止
check("收束只报告不阻止写入", ev.validate(d1) == [])

# ── 转折点：由相邻音符推导（C7 同键连击 / C8 换弓） ─────
def _e(iid, on, semi, eid, dur=100_000):
    return ev.Event(id=eid, instrument_id=iid, onset_us=on, release_us=on + dur,
                    pitch=ev.Pitch("C", 0, 4, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


d5 = doc([ev.Instrument("P1", "acoustic_grand_piano")],
         [_e(1, 0, 60, "L00000001", 100_000), _e(1, 110_000, 60, "L00000002", 100_000)])
check("C7 钢琴同键 10ms 连击 → 报", any(x.startswith("C7") for x in pl.check_playability(d5)),
      str(pl.check_playability(d5)))

d6 = doc([ev.Instrument("P1", "violin")],
         [_e(1, 0, 60, "L00000001", 100_000), _e(1, 100_000, 62, "L00000002", 100_000)])
check("C8 提琴无间隙换弓 → 报", any(x.startswith("C8") for x in pl.check_playability(d6)),
      str(pl.check_playability(d6)))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
