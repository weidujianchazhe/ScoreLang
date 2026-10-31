# -*- coding: utf-8 -*-
"""中文人声：拼音表 / 段结构 / 收束 / 合成 的测试。

人声的单位是**事件 + 段**：一个音一个事件，段是声母或韵母（带自己的时间）。
本套件不涉及汉字/歌词（那条路已移除）。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import ms_author as au
import ms_events as ev
import ms_io
import ms_semantics as ms
import ms_sing
import pinyin as py
import vocal_plan as vp

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def evt(i, onset, dur=500_000, semi=62):
    steps = {0: ("C", 0), 2: ("D", 0), 4: ("E", 0), 5: ("F", 0), 7: ("G", 0),
             9: ("A", 0), 11: ("B", 0)}
    step, alter = steps[semi % 12]
    return ev.Event(id=f"L{i:08d}", instrument_id=1, onset_us=onset, release_us=onset + dur,
                    pitch=ev.Pitch(step, alter, semi // 12 - 1, semi), release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 800, "relative_permille", "c", "measured"))


# ── 1) 拼音规范化与切分 ──────────────────────────────────
check("P1 yi→i", py.normalize("yi") == "i")
check("P2 wu→u", py.normalize("wu") == "u")
check("P3 yu→v", py.normalize("yu") == "v")
s = py.parse("长", "chang", 2)
check("P4 chang = ch+a+ng", [(g.kind, g.text) for g in s.segments]
      == [("initial", "ch"), ("nucleus", "a"), ("coda", "ng")],
      str([(g.kind, g.text) for g in s.segments]))
check("P5 xing 有介音 i",
      [g.text for g in py.parse("行", "xing").segments] == ["x", "i", "e", "ng"],
      str([g.text for g in py.parse("行", "xing").segments]))

# ── 2) 拼音 → 段（写谱侧便利函数）──────────────────────────
check("P6 vocal_units(chang) 三段",
      au.vocal_units("chang", 2) == [("initial", "ch", 2), ("nucleus", "a", 2),
                                     ("coda", "ng", 2)],
      str(au.vocal_units("chang", 2)))

# ── 3) 段带时间：写一个字（两个音，第二个省声母）──────────
units = au.vocal_units("chang", 2)
e1, s1 = au.write_vocal(units=units, onset_us=0, duration_us=500_000,
                        semitone=62, level="mp")
check("P7 段时长之和 = 音时长",
      abs(sum(x.release_us - x.onset_us for x in s1) - 500_000) <= 3,
      str([(x.kind, x.release_us - x.onset_us) for x in s1]))
check("P8 段顺序相接（首段从音头起）",
      s1[0].onset_us == 0 and all(a.release_us == b.onset_us for a, b in zip(s1, s1[1:])),
      str([(x.onset_us, x.release_us) for x in s1]))

e2, s2 = au.write_vocal(units=[u for u in units if u[0] != "initial"],
                        onset_us=500_000, duration_us=500_000, semitone=64,
                        binding=s1[0].binding_id, level="mp",
                        used_ids={x.id for x in e1})
check("P9 拖腔第二音同 binding、无声母",
      s2[0].binding_id == s1[0].binding_id and not any(x.kind == "initial" for x in s2))

doc = au.to_document(e1 + e2, instruments=[au.make_instrument("P1", "soprano")],
                     segments=s1 + s2)
check("P10 文档校验通过", ev.validate(doc) == [], str(ev.validate(doc)))

# ── 4) 收束：一个事件一个音，按时间排 ────────────────────
plan = vp.build_plan(doc)
check("P11 两个音 = 两个计划项", len(plan.syllables) == 2, str(len(plan.syllables)))
check("P12 音间转折 = 连音（同 binding 紧贴）",
      [t["kind"] for t in plan.turns] == ["liaison"], str(plan.turns))
check("P13 段计划沿用文件里的时间",
      abs(sum(g.dur_us for g in plan.syllables[0].segments) - 500_000) <= 3,
      str([g.dur_us for g in plan.syllables[0].segments]))

# ── 5) 合成 ─────────────────────────────────────────────
wav = ms_sing.sing(plan, doc)
check("P14 出声", float(np.abs(wav).max()) > 0.1, f"peak {float(np.abs(wav).max()):.2f}")
check("P15 时长合理", 0.4 < len(wav) / ms_sing.SR < 2.5, f"{len(wav)/ms_sing.SR:.2f}s")

# ── 6) 哼唱：没有段，按音高生成鼻音 ───────────────────────
hum = ev.MSDocument(events=[evt(1, 0, 500_000, 67)],
                    instruments=[ev.Instrument("P1", "voice_hum")])
hp = vp.build_plan(hum)
check("P16 哼唱无段也能出计划", len(hp.syllables) == 1 and hp.syllables[0].pinyin == "m",
      str([(x.pinyin, x.char) for x in hp.syllables]))
check("P17 哼唱出声", float(np.abs(ms_sing.sing(hp, hum)).max()) > 0.1)

# ── 7) 落盘往返 ─────────────────────────────────────────
text = ms_io.dump(doc)
check("P18 段随事件流往返字节一致", ms_io.dump(ms_io.parse(text)) == text)
check("P19 往返后段数不变", len(ms_io.parse(text).segments) == len(s1) + len(s2))

bad = [r for r in RESULTS if not r[1]]
for name, ok_, detail in RESULTS:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(RESULTS)} 项：通过 {len(RESULTS) - len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
