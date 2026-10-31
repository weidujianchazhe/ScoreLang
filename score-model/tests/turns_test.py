# -*- coding: utf-8 -*-
"""转折点结构测试（含时间可行性）。"""
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
import ms_playability as pl
import ms_semantics as ms
import ms_validate

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


_SPELL = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
          6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}


def _pitch(semi):
    step, alter = _SPELL[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def note(iid, eid, onset, semi, dur=100_000, inst=1):
    return ev.Event(id=eid, instrument_id=inst, onset_us=onset, release_us=onset + dur,
                    pitch=_pitch(semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


def doc(inst, events, turns=()):
    return ev.MSDocument(events=list(events), instruments=[ev.Instrument("P1", inst)],
                         turns=list(turns))


# 1) 往返（两音：前音 + 换弓）
d = doc("violin", [note(1, "L00000001", 0, 60), note(1, "L00000002", 200_000, 62)],
        [ev.TurnPoint("L00000002", "bow_change", 700)])
back = ms_io.parse(ms_io.dump(d))
check("T1 转折往返", [(t.event_id, t.kind, t.strength) for t in back.turns]
      == [("L00000002", "bow_change", 700)], str(back.turns))

# 2) 悬空转折
bad = doc("violin", [note(1, "L00000001", 0, 60), note(1, "L00000002", 200_000, 62)],
          [ev.TurnPoint("L00000009", "bow_change", 500)])
check("T2 悬空转折 → 拒绝", any("V16" in e for e in ms_validate.validate(bad)),
      str(ms_validate.validate(bad)))

# 3) 钢琴写换弓
bad2 = doc("acoustic_grand_piano", [note(1, "L00000001", 0, 60), note(1, "L00000002", 200_000, 62)],
           [ev.TurnPoint("L00000002", "bow_change", 500)])
check("T3 钢琴换弓 → 拒绝", any("不适用于" in e for e in ms_validate.validate(bad2)),
      str(ms_validate.validate(bad2)))

# 4/5) 有转折标记 → C8 不再报
two = doc("violin", [note(1, "L00000001", 0, 60), note(1, "L00000002", 100_000, 62)])
before = pl.check_playability(two)
two.turns = [ev.TurnPoint("L00000002", "bow_change", 800)]
after = pl.check_playability(two)
check("T4 未标记时报 C8", any(x.startswith("C8") for x in before), str(before))
check("T5 标记后不再报", not any(x.startswith("C8") for x in after), str(after))

# 6) 合成器：转折音头带来音色差异（breath 可单音）
x1 = make_audio.render(doc("flute", [note(1, "L00000001", 0, 60)]))
d2 = doc("flute", [note(1, "L00000001", 0, 60)], [ev.TurnPoint("L00000001", "breath", 1000)])
x2 = make_audio.render(d2)
check("T6 转折改变波形", not np.allclose(x1, x2))

# 7/8) V16b 时间可行性
ok = doc("acoustic_grand_piano",
         [note(1, "L00000001", 0, 60), note(1, "L00000002", 140_000, 60)],
         [ev.TurnPoint("L00000002", "retrigger", 800)])
check("T7 同键 40ms 再击 → 允许", ms_validate.validate(ok) == [], str(ms_validate.validate(ok)))

tight = doc("acoustic_grand_piano",
            [note(1, "L00000001", 0, 60), note(1, "L00000002", 105_000, 60)],
            [ev.TurnPoint("L00000002", "retrigger", 800)])
check("T8 同键 5ms 再击 → 拒绝",
      any("不可行" in e for e in ms_validate.validate(tight)), str(ms_validate.validate(tight)))

# 9/10/11) breath / restrike / mallet 的间隙因子
flute_tight = doc("flute", [note(1, "L00000001", 0, 60), note(1, "L00000002", 140_000, 62)],
                  [ev.TurnPoint("L00000002", "breath", 800)])
check("T9 长笛换气 40ms → 拒绝",
      any("breath" in e and "不可行" in e for e in ms_validate.validate(flute_tight)),
      str(ms_validate.validate(flute_tight)))

gtr_tight = doc("acoustic_guitar_nylon",
                [note(1, "L00000001", 0, 60), note(1, "L00000002", 110_000, 62)],
                [ev.TurnPoint("L00000002", "restrike", 800)])
check("T10 吉他重复拨弦 10ms → 拒绝",
      any("restrike" in e and "不可行" in e for e in ms_validate.validate(gtr_tight)),
      str(ms_validate.validate(gtr_tight)))

tim_tight = doc("timpani", [note(1, "L00000001", 0, 48), note(1, "L00000002", 130_000, 48)],
                [ev.TurnPoint("L00000002", "mallet", 800)])
check("T11 定音鼓换槌 30ms → 拒绝",
      any("mallet" in e and "不可行" in e for e in ms_validate.validate(tim_tight)),
      str(ms_validate.validate(tim_tight)))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
