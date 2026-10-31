# -*- coding: utf-8 -*-
"""`ornament-v1` 测试：展开结果必须时间连续、总长守恒、邻音由调用方提供。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_events as ev
import ms_ornament as orn
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def span(notes):
    return max(n["onset_us"] + n["duration_us"] for n in notes) - min(n["onset_us"] for n in notes)


# ── 短倚音：拍前、从前音借时 ────────────────────────────────
g = orn.expand("grace_short", onset_us=1_000_000, duration_us=400_000, main_semitone=60)
check("O1 短倚音=2 个音", len(g) == 2, str(len(g)))
check("O2 倚音在主音之前（拍前）", g[0]["onset_us"] < g[1]["onset_us"])
check("O3 倚音时长=主音 1/4", g[0]["duration_us"] == 100_000, str(g[0]["duration_us"]))
check("O4 主音时长不变（借的是前音时间）", g[1]["duration_us"] == 400_000)

# ── 长倚音：拍上、从主音借时 ────────────────────────────────
a = orn.expand("appoggiatura_long", onset_us=1_000_000, duration_us=400_000, main_semitone=60)
check("O5 长倚音从主音起点开始（拍上）", a[0]["onset_us"] == 1_000_000)
check("O6 长倚音占主音 1/2", a[0]["duration_us"] == 200_000, str(a[0]["duration_us"]))
check("O7 主音被缩短且不与倚音重叠", a[1]["onset_us"] == 1_200_000 and a[1]["duration_us"] == 200_000)
check("O8 长倚音总跨度不变", span(a) == 400_000, str(span(a)))

# ── 波音：主-上邻-主 ────────────────────────────────────────
m = orn.expand("mordent", onset_us=0, duration_us=600_000, main_semitone=60, upper_semitone=62)
check("O9 波音=3 个音", len(m) == 3)
check("O10 波音辅助音占 10%", m[1]["duration_us"] == 60_000, str(m[1]["duration_us"]))
check("O11 波音总长守恒", span(m) == 600_000, str(span(m)))
check("O12 波音辅助音用传入的邻音", m[1]["semitone"] == 62)

# ── 回音：上-主-下-主 ──────────────────────────────────────
t = orn.expand("turn", onset_us=0, duration_us=600_000, main_semitone=60,
               upper_semitone=62, lower_semitone=58)
check("O13 回音=4 个音", len(t) == 4)
check("O14 回音总长守恒", span(t) == 600_000, str(span(t)))
check("O15 回音顺序（上-主-下-主）",
      [n["semitone"] for n in t] == [62, 60, 58, 60], str([n["semitone"] for n in t]))

# ── 颤音：10 次/秒 ─────────────────────────────────────────
tr = orn.expand("trill", onset_us=0, duration_us=1_000_000, main_semitone=60, upper_semitone=62)
check("O16 颤音 1 秒至少 10 个音", len(tr) >= 10, str(len(tr)))
check("O17 颤音周期 100ms", tr[0]["duration_us"] == 100_000)
check("O18 颤音交替主音/上邻音", tr[0]["semitone"] == 60 and tr[1]["semitone"] == 62)
check("O19 颤音不越界（不超过主音终点）",
      all(n["onset_us"] + n["duration_us"] <= 1_000_000 for n in tr))
check("O20 颤音总跨度约等于主音时长", span(tr) == 1_000_000, str(span(tr)))

short = orn.expand("trill", onset_us=0, duration_us=50_000, main_semitone=60, upper_semitone=62)
check("O21 过短的颤音退化为一个主音", len(short) == 1 and short[0]["semitone"] == 60)

# ── 邻音必须由调用方提供 ───────────────────────────────────
for name, kw in (("mordent", {}), ("turn", {"upper_semitone": 62}), ("trill", {})):
    try:
        orn.expand(name, onset_us=0, duration_us=100_000, main_semitone=60, **kw)
    except ValueError:
        check(f"O22-{name} 缺邻音 → 拒绝", True)
    else:
        check(f"O22-{name} 缺邻音 → 拒绝", False, "应当 ValueError")

try:
    orn.expand("acciaccatura", onset_us=0, duration_us=100_000, main_semitone=60)
except KeyError:
    check("O23 未知装饰音拒绝", True)
else:
    check("O23 未知装饰音拒绝", False)

try:
    orn.expand("grace_short", onset_us=0, duration_us=0, main_semitone=60)
except ValueError:
    check("O24 零时长主音拒绝", True)
else:
    check("O24 零时长主音拒绝", False)

# ── 展开结果能构造合法 MS ─────────────────────────────────
tbl = orn.table()
check("O25 表含版本与关键比例",
      tbl["version"] == "ornament-v1" and tbl["trill_rate_hz"] == 10
      and tbl["grace_short_pm"] == 250 and tbl["appoggiatura_long_pm"] == 500, str(tbl))

events = []
for i, n in enumerate(g):
    semi = n["semitone"]
    events.append(ev.Event(id=f"g{i}", instrument_id=1, onset_us=n["onset_us"],
                           pitch=ev.Pitch("C", semi - 60, 4, semi),   # C4=60, C#4=61
                           release_us=n["onset_us"] + n["duration_us"],
                           release_state="given",
                           dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "notated_inferred")))
doc = ev.MSDocument(events=events)
check("O26 展开结果能构造合法 MS 乐谱模型", ev.validate(doc) == [], str(ev.validate(doc)))

# ── O27：装饰音展开时主音拼写不得丢失 ──
import ms_author as _au
_evs = _au.write_note(onset_us=0, duration_us=1_000_000, semitone=70,
                      spelling=("B", -1, 4), ornament="trill",
                      instrument_type="acoustic_grand_piano", used_ids=set())
check("O27 主音保留 Bb 拼写（不是 A#）",
      any(e.pitch.step == "B" and e.pitch.alter == -1 for e in _evs),
      str([(e.pitch.step, e.pitch.alter) for e in _evs]))


# ── O28/29：调内邻音（upper/lower）可写 ──
import ms as _ms
_g = _ms.start(bpm=100, instruments=[{"type": "piano"}])
_g.note(1, "C5", beat=0, beats=1, ornament="trill", upper="D5")
_s = _g.finish()
_p = {(e.pitch.step, e.pitch.alter) for e in _s._doc.events}
check("O28 trill upper=D5 用调内邻音", ("D", 0) in _p and ("C", 1) not in _p, str(_p))
_g2 = _ms.start(bpm=100, instruments=[{"type": "piano"}])
_g2.note(1, "C5", beat=0, beats=1, ornament="trill")
_s2 = _g2.finish()
_p2 = {(e.pitch.step, e.pitch.alter) for e in _s2._doc.events}
check("O29 默认邻音为半音上方", ("C", 1) in _p2, str(_p2))

# ── O30/31：grace/appoggiatura 的邻音与展开 ──
_g3 = _ms.start(bpm=100, instruments=[{"type": "piano"}])
_g3.note(1, "C5", beat=0, beats=1, ornament="grace_short", grace="F#5")
_p3 = {(e.pitch.step, e.pitch.alter) for e in _g3.finish()._doc.events}
check("O30 grace 显式邻音 F#5", ("F", 1) in _p3, str(_p3))
_g4 = _ms.start(bpm=100, instruments=[{"type": "piano"}])
_g4.note(1, "C5", beat=0, beats=1, ornament="appoggiatura_long")
_ev4 = _g4.finish()._doc.events
check("O31 长倚音不再同音", len({(e.pitch.step, e.pitch.alter) for e in _ev4}) == 2,
      str([(e.pitch.step, e.pitch.alter) for e in _ev4]))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
