# -*- coding: utf-8 -*-
"""导入器测试：MusicXML → MS、MIDI → MS、以及 MIDI 往返。"""
from __future__ import annotations

import sys as _sys
import tempfile
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

from pathlib import Path

import ms_events as ev
import ms_import as mi
import ms_import_midi as imi
import ms_io as mj
import ms_midi as mm
import ms_semantics as ms

HERE = ROOT
FIX = HERE / "fixtures" / "real"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# ── MusicXML ────────────────────────────────────────────────
doc, rep = mi.import_musicxml(FIX / "k545_exp.musicxml", max_measures=8)
check("X1 8 小节 122 音", rep["measures"] == 8 and rep["notes"] == 122,
      f"{rep['measures']}/{rep['notes']}")
check("X2 读到 tempo 132", abs(rep["tempo_bpm"] - 132.0) < 0.01, str(rep["tempo_bpm"]))
check("X3 导入结果通过校验", ev.validate(doc) == [], str(ev.validate(doc))[:60])
check("X4 含和弦（同 onset 多音）", rep["chords"] == 7, str(rep["chords"]))
check("X5 首音 C5=72", doc.events[0].pitch.semitone == 72, str(doc.events[0].pitch.semitone))
check("X6 调号/拍号记为缺口", any(g["code"] == "notation_context" for g in doc.gaps))

# 节拍换算：132bpm → 每四分 454545µs；第二个音在 200/480 拍处
sec = [e for e in doc.events if e.pitch.semitone == 76][0]
check("X7 时间换算与 tempo 一致（909090µs）", sec.onset_us == 909090, str(sec.onset_us))

# 力度：用一个带 <dynamics><mf/> 的最小 MusicXML 验换算（K545 前 8 小节本身无力度记号）
SYNTH = """<?xml version="1.0"?><score-partwise version="2.0"><part id="P1">
<measure number="1"><attributes><divisions>1</divisions></attributes>
<direction><direction-type><dynamics><mf/></dynamics></direction-type></direction>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
</measure></part></score-partwise>"""
tmp = Path(tempfile.gettempdir()) / "pianomusic_test" / "_synth_dyn.musicxml"
tmp.parent.mkdir(exist_ok=True)
tmp.write_text(SYNTH, encoding="utf-8")
dyn_doc, _ = mi.import_musicxml(tmp)
check("X8 力度记号 mf → 1250‰ 且来源为 notated_inferred",
      dyn_doc.events[0].dynamics.permille == 1250
      and dyn_doc.events[0].dynamics.src == "notated_inferred",
      str(dyn_doc.events[0].dynamics))
tmp.unlink(missing_ok=True)

# 小样例（twinkle）也能导
doc2, rep2 = mi.import_musicxml(HERE / "fixtures" / "twinkle_theme.musicxml")
check("X9 twinkle 可导入且合法", rep2["notes"] > 0 and ev.validate(doc2) == [],
      str(rep2["notes"]))

# ── MIDI 往返 ──────────────────────────────────────────────
d = ev.MSDocument(events=[
    ev.Event(id="a", instrument_id=1, onset_us=0, pitch=ev.Pitch("C", 0, 4, 60),
             release_us=500_000, release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
    ev.Event(id="b", instrument_id=1, onset_us=500_000, pitch=ev.Pitch("E", 0, 4, 64),
             release_us=1_000_000, release_state="given",
             dynamics=ev.Dynamics(ms.VALUE, 1250, "relative_permille", "cal", "measured")),
], pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)])
data, _ = mm.write_midi(d, time_base_us=500_000)
back, rep3 = imi.import_midi(data)
check("X10 MIDI 往返音数一致", rep3["notes"] == 2, str(rep3["notes"]))
check("X11 MIDI 往返音高一致", [e.pitch.semitone for e in back.events] == [60, 64],
      str([e.pitch.semitone for e in back.events]))
check("X12 MIDI 往返起点一致", [e.onset_us for e in back.events] == [0, 500_000],
      str([e.onset_us for e in back.events]))
check("X13 力度往返（1000→64→1000、1250→80→1250）",
      [e.dynamics.permille for e in back.events] == [1000, 1250],
      str([e.dynamics.permille for e in back.events]))
check("X14 踏板往返成段", len(back.pedals) == 1 and back.pedals[0].kind == "sustain",
      str([(p.kind, p.start_us, p.end_us) for p in back.pedals]))
check("X15 MIDI 导入结果合法", ev.validate(back) == [], str(ev.validate(back))[:60])

# ── 残缺 MIDI：缺 note-off 要记缺口，不伪造 ───────────────
# 手工构造：只有一个 note-on（无对应 off）
import struct
thd = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480)
trk = b"\x00\x90\x3c\x40"                      # note-on C4 vel64
trk_data = b"MTrk" + struct.pack(">I", len(trk)) + trk
try:
    bad, rep4 = imi.import_midi(thd + trk_data)
    gap_ok = any(g["code"] == "missing_note_off" for g in rep4["gaps"]) and rep4["notes"] == 0
    check("X16 缺 note-off → 记缺口且不产生事件", gap_ok, str(rep4["gaps"]))
except ValueError as e:
    check("X16 缺 note-off → 记缺口且不产生事件", "校验" in str(e), str(e)[:60])

# ── .mxl 压缩容器 ──────────────────────────────────────────
import zipfile
mxl = Path(tempfile.gettempdir()) / "pianomusic_test" / "_t.mxl"
mxl.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(mxl, "w") as z:
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0"?><container><rootfiles>'
               '<rootfile full-path="s.musicxml"/></rootfiles></container>')
    z.writestr("s.musicxml",
               (HERE / "fixtures" / "twinkle_theme.musicxml").read_text(encoding="utf-8"))
dm, rm = mi.import_musicxml(mxl)
check("X18 .mxl 与直接 MusicXML 结果一致", rm["notes"] == rep2["notes"],
      f"{rm['notes']} vs {rep2['notes']}")
mxl.unlink(missing_ok=True)

# ── 含音色切换（0xC0）的 MIDI 不应被拒（Basic Pitch 等工具会写） ──
thd2 = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480)
trk2 = (b"\x00\xc0\x00"                       # program change
        b"\x00\x90\x3c\x40" b"\x83\x60\x80\x3c\x40")
trk2_data = b"MTrk" + struct.pack(">I", len(trk2)) + trk2
ok2, rep5 = imi.import_midi(thd2 + trk2_data)
check("X19 含 0xC0 音色切换仍可导入（跳过并计数）",
      rep5["notes"] == 1 and mm.read_midi(thd2 + trk2_data)["skipped"] >= 1,
      str(rep5["notes"]))

# ── 空文档也能稳定往返 ───────────────────────────────────
empty = ev.MSDocument(events=[])
txt = mj.dumps(empty)
check("X17 空文档可序列化", mj.loads(txt).events == [])

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
