# -*- coding: utf-8 -*-
"""S02 同步测试：和弦共享声部（Q6）、损失计数、乐器/歌词随投影、多乐器往返。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_semantics as ms
import ms_to_s02
import s02_to_ms

TB = 500_000
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def pitch(semi):
    b = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
         6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = b[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def evt(iid, onset, semi, eid, dur=200_000):
    return ev.Event(id=eid, instrument_id=iid, onset_us=onset, release_us=onset + dur,
                    pitch=pitch(semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


def doc(inst, events, segments=()):
    d = ev.MSDocument(events=list(events), instruments=list(inst),
                      segments=list(segments))
    d.piano_count = len(inst)
    return d


piano = [ev.Instrument("P1", "acoustic_grand_piano")]

# ── 1) 三音和弦 → 单声部（Q6） ───────────────────────────
chord = doc(piano, [evt(1, 0, 60, "L00000001"), evt(1, 0, 64, "L00000002"), evt(1, 0, 67, "L00000003")])
s1, l1 = ms_to_s02.to_s02(chord, time_base_us=TB)
check("S1 同 onset 三音共享一个声部", len({n.voice for n in s1.notes}) == 1,
      str([n.voice for n in s1.notes]))
check("S2 和弦不再记声部损失", l1 == [], str(l1))

# ── 2) 真重叠（不同 onset）→ 新声部，记一条损失 ──────────
overlap = doc(piano, [evt(1, 0, 60, "L00000001", 400_000), evt(1, 100_000, 64, "L00000002", 400_000)])
s2, l2 = ms_to_s02.to_s02(overlap, time_base_us=TB)
check("S3 真重叠才新开声部", len({n.voice for n in s2.notes}) == 2, str([n.voice for n in s2.notes]))
check("S4 新开声部记一条损失", len(l2) == 1 and l2[0]["item"].startswith("voice_created:"), str(l2))

# ── 3) 乐器表随投影走 ──────────────────────────────────
multi = doc([ev.Instrument("P1", "acoustic_grand_piano"),
             ev.Instrument("P2", "violin", "solo", "strings_1")],
            [evt(1, 0, 60, "L00000001"), evt(2, 0, 72, "L00000002")])
s3, _ = ms_to_s02.to_s02(multi, time_base_us=TB)
check("S5 S02 带乐器表", len(s3.instruments) == 2 and s3.instruments[1]["type"] == "violin",
      str(s3.instruments))
check("S6 S02 音符带乐器号", sorted(n.instrument_id for n in s3.notes) == [1, 2],
      str([n.instrument_id for n in s3.notes]))
check("S7 S02 schema 2", s3.schema_version == "s02-2", s3.schema_version)

# ── 4) 人声段投影成 S02 segments（s02-2 起有槽位）────────
with_seg = doc(piano, [evt(1, 0, 60, "L00000001")],
               segments=[ev.VoiceSegment("B00001", 0, "nucleus", "a", 1,
                                         event_id="L00000001", binding_id="B00001", lang="zh")])
s4, losses4 = ms_to_s02.to_s02(with_seg, time_base_us=TB)
check("S8 发声段投影成 segments",
      len(s4.segments) == 1 and s4.segments[0].text == "a"
      and s4.segments[0].binding_id == "B00001",
      str([(x.kind, x.text) for x in s4.segments]))
check("S9 S02 校验通过", s4.validate() == [], str(s4.validate()))

# ── 5) 多乐器反向回 MS ─────────────────────────────────
back, _gaps = s02_to_ms.from_s02(s3, time_base_us=TB)
check("S10 多乐器往返保留乐器号", sorted(e.instrument_id for e in back.events) == [1, 2],
      str([e.instrument_id for e in back.events]))
check("S11 往返保留乐器表", len(back.instruments) == 2, str(back.instruments))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
