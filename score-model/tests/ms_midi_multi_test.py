# -*- coding: utf-8 -*-
"""多乐器 MIDI 导出测试：Program Change / 声部组合并 / 多文件溢出 / 鼓组通道。"""
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

TB = 500_000
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


SPELL = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
         5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
         10: ("B", -1), 11: ("B", 0)}


def pitch(semi):
    step, alter = SPELL[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def doc_with(instruments, events, channels="per_instance", segments=()):
    d = ev.MSDocument(channels=channels, events=events, instruments=instruments,
                      segments=list(segments))
    d.piano_count = len(instruments)
    return d


def ev1(iid, onset, semi=60, eid=None):
    return ev.Event(id=eid or f"L{onset}_{iid}", instrument_id=iid, onset_us=onset,
                    pitch=pitch(semi), release_us=onset + 250_000, release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "c", "measured"))


# ── 1) per_instance：两件乐器 → 两个通道 + 各一条 Program Change ──
inst = [ev.Instrument("P1", "acoustic_grand_piano", "steinway_d"),
        ev.Instrument("P2", "violin")]
d = doc_with(inst, [ev1(1, 0), ev1(2, 0, 76)])
files, rep = mm.write_midi_files(d, time_base_us=TB)
check("X1 单文件（两件乐器）", len(files) == 1, str(rep["files"]))
check("X2 两件乐器两通道", sorted(rep["channels"].values()) == [0, 1], str(rep["channels"]))
check("X3 每个通道都发 Program Change",
      sorted(rep["per_file"][0]["programs"].keys()) == [0, 1],
      str(rep["per_file"][0]["programs"]))

# ── 2) per_section：同声部合并成一个通道 ──
inst2 = [ev.Instrument("P1", "violin", None, "strings_1"),
         ev.Instrument("P2", "violin", None, "strings_1"),
         ev.Instrument("P3", "violin", None, "strings_2")]
d2 = doc_with(inst2, [ev1(1, 0), ev1(2, 0), ev1(3, 0)], channels="per_section")
_, rep2 = mm.write_midi_files(d2, time_base_us=TB)
check("X4 per_section 同声部合并", rep2["channels"][1] == rep2["channels"][2],
      str(rep2["channels"]))
check("X5 不同声部不同通道", rep2["channels"][3] != rep2["channels"][1],
      str(rep2["channels"]))
check("X6 合并写入报告", len(rep2["channel_merged"]) == 1,
      str(rep2["channel_merged"]))

# ── 3) 溢出：20 个实例 → 2 个文件 ──
inst3 = [ev.Instrument(f"P{i}", "acoustic_grand_piano") for i in range(1, 21)]
d3 = doc_with(inst3, [ev1(i, i * 1000) for i in range(1, 21)])
files3, rep3 = mm.write_midi_files(d3, time_base_us=TB)
check("X7 超 16 通道自动分文件", len(files3) == 2, str(rep3["files"]))
check("X8 第二文件有乐器", any(v["file"] == 2 for v in rep3["channel_map"].values()))

# ── 4) 鼓组走通道 10（0-based 9）────────────────────────────
inst4 = [ev.Instrument("P1", "timpani"), ev.Instrument("P2", "violin")]
d4 = doc_with(inst4, [ev1(1, 0), ev1(2, 0, 76)])
_, rep4 = mm.write_midi_files(d4, time_base_us=TB)
check("X9 打击乐走通道 10", rep4["channels"][1] == 9, str(rep4["channels"]))
check("X10 打击乐不发 Program Change", 9 not in rep4["per_file"][0]["programs"])

# ── 5) 人声段不写 MIDI 歌词 meta（MS 的段没有对端槽位）──────
d5 = doc_with([ev.Instrument("P1", "choir_aahs")], [ev1(1, 0, 72, eid="L00000001")],
              segments=[ev.VoiceSegment("B00001", 0, "nucleus", "a", 1,
                                        event_id="L00000001", binding_id="B00001", lang="zh")])
files5, rep5 = mm.write_midi_files(d5, time_base_us=TB)
data5 = files5[0]
check("X11 人声也能出 MIDI（不崩）", len(data5) > 20)
check("X12 不发 Lyric meta（段不是歌词）", b"\xFF\x05" not in data5)

import ms_io as _io
back5 = _io.parse(_io.dump(d5))
check("X13 发声段往返（时间/绑定保留）",
      len(back5.segments) == 1 and back5.segments[0].binding_id == "B00001", str(back5.segments))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
