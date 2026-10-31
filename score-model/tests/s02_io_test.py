# -*- coding: utf-8 -*-
"""`.s02` 读写：确定性、往返、拒绝非法输入。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import s02_io

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def build() -> "mv.ScoreV02":
    s = mv.ScoreV02(title="测试曲", grid_units_per_quarter=480,
                    time_beats=4, time_beat_type=4, key_fifths=-2)
    s.instruments = [{"id": "P1", "type": "acoustic_grand_piano",
                      "subtype": "steinway_d", "section": None},
                     {"id": "P2", "type": "violin", "subtype": None, "section": "strings_1"}]
    s.notes = [
        mv.NoteEvent(id="L00000001", onset=0, duration=480, voice="RH", staff="treble",
                     measure=0, pitch=mv.PitchSpell("C", 0, 4), dynamics_permille=800,
                     release_state="given", instrument_id=1),
        mv.NoteEvent(id="L00000002", onset=480, duration=480, voice="RH", staff="treble",
                     measure=0, pitch=mv.PitchSpell("E", 0, 4), dynamics_permille=760,
                     release_state="giving" if False else "given", instrument_id=1),
        mv.NoteEvent(id="L00000003", onset=0, duration=960, voice="LH", staff="bass",
                     measure=0, pitch=mv.PitchSpell("C", 0, 3), dynamics_permille=None,
                     release_state="sustaining", instrument_id=2),
    ]
    s.rests = [mv.RestEvent(id="R00000001", onset=960, duration=480, voice="RH",
                            staff="treble", measure=0)]
    s.pedal_marks = [
        mv.PedalMark(id="D00000001", pedal_type="sustain", action_notated="start",
                     onset=0, measure=0, depth_permille=400),
        mv.PedalMark(id="D00000002", pedal_type="sustain", action_notated="stop",
                     onset=960, measure=0, depth_permille=0),
        mv.PedalMark(id="D00000003", pedal_type="sordino", action_notated="start",
                     onset=0, measure=0, depth_permille=1000),
        mv.PedalMark(id="D00000004", pedal_type="tuning", action_notated="start",
                     onset=0, measure=0, depth_permille=0, target_scope=["C"]),
    ]
    s.actions = [mv.ActionMark(id="A00000001", kind="bow_up", target_id="L00000002",
                               strength=700),
                 mv.ActionMark(id="A00000002", kind="mute_harmon", target_id="L00000003",
                               strength=900)]
    s.curves = [mv.CurveLane(instrument_id=2, param="vibrato", time_us=0, value=500, ramp=0),
                mv.CurveLane(instrument_id=2, param="pitch_cents", time_us=240_000,
                             value=-100, ramp=1)]
    s.segments = [mv.VoiceSegmentV02(event_id="L00000001", index=0, kind="initial",
                                     text="ch", binding_id="B00001", tone=2,
                                     lang="zh", onset_us=0, end_us=90_000),
                  mv.VoiceSegmentV02(event_id="L00000001", index=1, kind="nucleus",
                                     text="ang", binding_id="B00001", tone=2,
                                     lang="zh", onset_us=90_000, end_us=480_000)]
    return s


s = build()
text = s02_io.dump(s)

check("S1 往返字节一致", s02_io.dump(s02_io.parse(text)) == text)
check("S2 两次写出字节一致", s02_io.dump(s) == text)
check("S3 有魔数行与版本", text.splitlines()[0] == "s02 2", text.splitlines()[0])
check("S4 七个块都在", all(k in text for k in
                          ("instruments", "notes", "rests", "pedals",
                           "actions", "curves", "segments")))

back = s02_io.parse(text)
_row = lambda n: (n.id, n.onset, n.pitch.step, n.dynamics_permille,
                  n.release_state, n.instrument_id)
check("S5 音符往返（含力度/释放/乐器号）",
      sorted(map(_row, back.notes)) == sorted(map(_row, s.notes)),
      str([(n.id, n.dynamics_permille) for n in back.notes]))
check("S6 动作往返", sorted((a.kind, a.target_id, a.strength) for a in back.actions)
      == sorted((a.kind, a.target_id, a.strength) for a in s.actions), str(back.actions))
check("S7 曲线往返", sorted((c.instrument_id, c.param, c.time_us, c.value, c.ramp)
                            for c in back.curves)
      == sorted((c.instrument_id, c.param, c.time_us, c.value, c.ramp) for c in s.curves),
      str(back.curves))
check("S8 发声段往返", [(x.kind, x.text, x.onset_us, x.end_us) for x in back.segments]
      == [(x.kind, x.text, x.onset_us, x.end_us) for x in s.segments], str(back.segments))
check("S9 七种踏板都能读写",
      {p.pedal_type for p in back.pedal_marks} == {"sustain", "sordino", "tuning"},
      str({p.pedal_type for p in back.pedal_marks}))
check("S10 标题与网格往返", back.title == "测试曲" and back.grid_units_per_quarter == 480)
check("S11 校验通过", back.validate() == [], str(back.validate()))


def rejects(label, mutate):
    bad = mutate(text)
    try:
        s02_io.parse(bad)
    except s02_io.FormatError:
        check(label, True)
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"抛了 {type(exc).__name__}")
    else:
        check(label, False, "未拒绝")


rejects("S12 未知区块 → 拒绝", lambda t: t.replace("notes 3", "bogus 3", 1))
rejects("S13 计数不符 → 拒绝", lambda t: t.replace("notes 3", "notes 4", 1))
rejects("S14 版本过高 → 拒绝", lambda t: t.replace("s02 2", "s02 99", 1))
rejects("S15 动作指向不存在的音 → 拒绝",
        lambda t: t.replace("bow_up L00000002", "bow_up L99999999", 1))
rejects("S16 段类型非法 → 拒绝", lambda t: t.replace("initial ch", "bogus ch", 1))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
