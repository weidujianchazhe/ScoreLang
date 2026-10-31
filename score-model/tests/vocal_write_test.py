# -*- coding: utf-8 -*-
"""人声写入测试（事件 + 段）：10 字样例与生成器。

模型：**一个事件 = 一个音**；音的发声内容由挂在它下面的**段**给出，
一段就是一个声母或一个韵母（initial / medial / nucleus / coda）。

覆盖：
  · `ms_author.vocal_units` / `write_vocal`：拼音→段、写音+段、非法输入拒绝
  · 拖腔：同一个 `binding` 的第二个音省掉声母
  · 收束层：段时长分配、段级声调、音间转折（连音 / 重起 / 换气）
  · 10 字成品：14 个音 / 10 个 binding / 40 个段；9 列段行往返；渲染

生成成品（谱 + 声音）：
    python -B tests/vocal_write_test.py --emit
      → pianomusic/inbox/vocal_10chars.ms
      → pianomusic/inbox/vocal_10chars.wav
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import tempfile

import numpy as np

import make_audio
import ms_author as au
import ms_io
import ms_sing
import ms_validate
import vocal_plan as vp

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ValueError:
        return True
    return False


# ── 1) 拼音 → 段（写谱侧，不入文件）────────────────────────
check("S1 chang → ch/a/ng",
      au.vocal_units("chang", 2) == [("initial", "ch", 2), ("nucleus", "a", 2),
                                     ("coda", "ng", 2)],
      str(au.vocal_units("chang", 2)))
check("S2 xing 有介音段",
      [u[1] for u in au.vocal_units("xing")] == ["x", "i", "e", "ng"],
      str(au.vocal_units("xing")))
check("S3 零声母字没有 initial 段",
      not any(u[0] == "initial" for u in au.vocal_units("ye")))

# ── 2) 写一个音 + 它的段 ─────────────────────────────────
units = au.vocal_units("chang", 2)
evs, segs = au.write_vocal(units=units, onset_us=0, duration_us=500_000,
                           semitone=62, level="mp")
check("S4 一个音 = 一个事件", len(evs) == 1 and evs[0].id == "L00000001", evs[0].id)
check("S5 三个段，index 0..2", [(s.index, s.kind) for s in segs]
      == [(0, "initial"), (1, "nucleus"), (2, "coda")],
      str([(s.index, s.kind) for s in segs]))
check("S6 段共享一个 binding", len({s.binding_id for s in segs}) == 1
      and segs[0].binding_id.startswith("B"), segs[0].binding_id)
check("S7 段挂在事件上", all(s.event_id == evs[0].id for s in segs))
check("S8 段带声调", [s.tone for s in segs] == [2, 2, 2])

# ── 3) 非法输入拒绝 ─────────────────────────────────────
check("S9 段类型非法 → 拒绝",
      raises(au.write_vocal, units=[("vowel", "a", 1)], onset_us=0,
             duration_us=500_000, semitone=60))
check("S10 段文本为空 → 拒绝",
      raises(au.write_vocal, units=[("nucleus", "", 1)], onset_us=0,
             duration_us=500_000, semitone=60))
check("S11 声调越界 → 拒绝",
      raises(au.write_vocal, units=[("nucleus", "a", 9)], onset_us=0,
             duration_us=500_000, semitone=60))
check("S12 时长非正 → 拒绝",
      raises(au.write_vocal, units=[("nucleus", "a", 1)], onset_us=0,
             duration_us=0, semitone=60))
check("S13 turn 非 0/1 → 拒绝",
      raises(au.write_vocal, units=[("nucleus", "a", 1)], onset_us=0,
             duration_us=500_000, semitone=60, turn=2))
check("S14 空 units → 拒绝",
      raises(au.write_vocal, units=[], onset_us=0, duration_us=500_000, semitone=60))


# ── 4) 10 字成品 ────────────────────────────────────────
# 「长夜行 · 天未明 · 晨雾静深」：10 个字 → 14 个音
# (字, 拼音, 声调, [(起点, 时长, 半音, 是否重起)])
PIECE = [
    ("长", "chang", 2, [(0, 500_000, 62, 0), (500_000, 500_000, 64, 0)]),      # 连音
    ("夜", "ye", 4, [(1_000_000, 500_000, 65, 0), (1_500_000, 500_000, 64, 1)]),  # 重起
    ("行", "xing", 2, [(2_000_000, 500_000, 62, 0), (2_650_000, 500_000, 57, 0)]),  # 换气
    ("天", "tian", 1, [(3_150_000, 750_000, 65, 0)]),
    ("未", "wei", 4, [(3_900_000, 500_000, 64, 0)]),
    ("明", "ming", 2, [(4_400_000, 500_000, 62, 0), (4_900_000, 750_000, 60, 0)]),  # 连音
    ("晨", "chen", 2, [(5_650_000, 500_000, 62, 0)]),
    ("雾", "wu", 4, [(6_150_000, 500_000, 64, 0)]),
    ("静", "jing", 4, [(6_650_000, 750_000, 65, 0)]),
    ("深", "shen", 1, [(7_400_000, 1_000_000, 62, 0)]),
]


def build_piece():
    events, segments, ids, binds = [], [], set(), set()
    for _char, py, tone, notes in PIECE:
        units = au.vocal_units(py, tone)
        binding = None
        for k, (onset, dur, semi, restart) in enumerate(notes):
            use = units if k == 0 else [u for u in units if u[0] != "initial"]
            ee, ss = au.write_vocal(units=use, onset_us=onset, duration_us=dur,
                                    semitone=semi, binding=binding, turn=restart,
                                    level="mp", used_ids=ids, used_bindings=binds)
            events += ee
            segments += ss
            ids |= {e.id for e in ee}
            binds |= {s.binding_id for s in ss}
            binding = ss[0].binding_id
    doc = au.to_document(events, instruments=[au.make_instrument("P1", "soprano")],
                         segments=segments)
    return doc


doc = build_piece()
check("S15 10 字 → 14 音 / 14 事件", len(doc.events) == 14
      and len({s.event_id for s in doc.segments}) == 14,
      f"{len(doc.events)} 事件 / {len({s.event_id for s in doc.segments})} 有段音")
check("S16 10 个 binding", len({s.binding_id for s in doc.segments}) == 10,
      str(len({s.binding_id for s in doc.segments})))
check("S17 段总数 41", len(doc.segments) == 41, str(len(doc.segments)))
check("S18 文档校验通过（V18 段索引/声调）", ms_validate.validate(doc) == [],
      str(ms_validate.validate(doc)))

text = ms_io.dump(doc)
back = ms_io.parse(text)
check("S19 段行往返：字节一致", ms_io.dump(back) == text)
check("S20 往返后段字段一致",
      [(s.event_id, s.index, s.kind, s.text, s.binding_id, s.tone, s.turn) for s in back.segments]
      == [(s.event_id, s.index, s.kind, s.text, s.binding_id, s.tone, s.turn) for s in doc.segments])
check("S21 往返后校验通过", ms_validate.validate(back) == [], str(ms_validate.validate(back)))

# ── 5) 收束层：一个事件一个音、段决定内容 ─────────────────
plan = vp.build_plan(back)
check("S22 计划 = 14 个音（一个事件一个音）", len(plan.syllables) == 14,
      str(len(plan.syllables)))
check("S23 每个音的段来自文件（不是查字）",
      [s.units for s in plan.syllables[:3]]
      == [[("initial", "ch"), ("nucleus", "a"), ("coda", "ng")],
          [("nucleus", "a"), ("coda", "ng")],
          [("medial", "i"), ("nucleus", "e")]],
      str([s.units for s in plan.syllables[:3]]))
check("S24 段时长之和 = 音时长",
      all(abs(sum(g.dur_us for g in s.segments) - s.dur_us) <= 5 for s in plan.syllables))
check("S25 首音有声母、拖腔后续音没有",
      [any(g.kind == "initial" for g in s.segments) for s in plan.syllables[:4]]
      == [True, False, False, False],
      str([any(g.kind == "initial" for g in s.segments) for s in plan.syllables[:4]]))
check("S26 转折：连音 / 重起 / 换气 / 连音",
      [t["kind"] for t in plan.turns] == ["liaison", "restrike", "breath", "liaison"],
      str([t["kind"] for t in plan.turns]))
check("S27 段级声调进计划（第 4 段 tone=4 → 夜）",
      all(g.tone == 4 for g in next(s for s in plan.syllables
                                    if s.units and s.units[0][1] == "i").segments))
check("S28 音高随音（一个事件一个音高）",
      [back.events[i].pitch.semitone for i in range(6)] == [62, 64, 65, 64, 62, 57],
      str([e.pitch.semitone for e in back.events[:6]]))

# ── 6) 渲染与落盘 ───────────────────────────────────────
wav = ms_sing.sing(plan, back)
SR = ms_sing.SR
check("S29 出声", float(np.abs(wav).max()) > 0.1, f"peak {float(np.abs(wav).max()):.2f}")
check("S30 时长 ≈ 8.4s + 0.3s 收尾", abs(len(wav) / SR - 8.7) < 0.3, f"{len(wav)/SR:.2f}s")
starts = sorted(s.onset_us for s in plan.syllables)
check("S31 每个音的起点都出声",
      all(float(np.abs(wav[int(t / 1e6 * SR):int((t + 250_000) / 1e6 * SR)]).max()) > 0.02
          for t in starts),
      str({round(t / 1e6, 2): round(float(np.abs(wav[int(t / 1e6 * SR):int((t + 250_000) / 1e6 * SR)]).max()), 2)
           for t in starts}))

with tempfile.TemporaryDirectory() as td:
    p = _Path(td) / "vocal_10chars.ms"
    p.write_text(text, encoding="utf-8")
    again = ms_io.parse(p.read_text(encoding="utf-8"))
    check("S32 落盘再读回：同一文档", ms_io.dump(again) == text and len(again.segments) == 41)
    mix = make_audio.render(again)
    check("S33 make_audio 认人声（段结构也走人声分支）",
          float(np.abs(mix).max()) > 0.2, f"peak {float(np.abs(mix).max()):.2f}")

if "--emit" in _sys.argv:
    out_dir = ROOT.parent / "inbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    ms_path = out_dir / "vocal_10chars.ms"
    wav_path = out_dir / "vocal_10chars.wav"
    ms_path.write_text(text, encoding="utf-8")
    make_audio.write_wav(make_audio.render(back), wav_path)
    print(f"写出 {ms_path}（{ms_path.stat().st_size} 字节）")
    print(f"写出 {wav_path}（{wav_path.stat().st_size} 字节）")

# ── W34/35：连续两个 vocal 音不得复用 binding ──
from ms_author import write_vocal as _wv
_ub = set()
_u = [("initial", "ch", 2), ("nucleus", "a", 2)]
_e1, _s1 = _wv(units=_u, onset_us=0, duration_us=500_000, semitone=60,
              used_bindings=_ub)
_e2, _s2 = _wv(units=_u, onset_us=600_000, duration_us=500_000, semitone=62,
              used_bindings=_ub)
check("W34 连续 vocal 的 binding 不同",
      _s1[0].binding_id != _s2[0].binding_id,
      f"{_s1[0].binding_id} vs {_s2[0].binding_id}")
check("W35 used_bindings 已回写", len(_ub) >= 2, str(sorted(_ub)))


fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
