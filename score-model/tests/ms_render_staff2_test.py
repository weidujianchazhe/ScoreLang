# -*- coding: utf-8 -*-
"""五线规范排版测试（II-3）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re

import ms_events as ev
import ms_render as ro
import ms_render_staff2 as st
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def note(semi, onset=0, dur=500_000):
    return ev.Event(id=f"n{semi}_{onset}", instrument_id=1, onset_us=onset, pitch=pitch(semi),
                    release_us=onset + dur, release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "notated_inferred"))


def count(svg, cls):
    return len(re.findall(rf'class="{cls}"', svg))


opts = ro.RenderOptions(meter=(4, 4), time_base_us=500_000, clef="treble")

# ── 单谱表 ─────────────────────────────────────────────────
d = ev.MSDocument(events=[note(64, 0), note(67, 500_000)])   # E4 / G4，均在五线内
svg = st.render_staff2(d, opts)
check("S1 单谱表 5 条线", count(svg, "staffline") == 5, str(count(svg, "staffline")))
check("S2 两个符头", count(svg, "note") == 2, str(count(svg, "note")))
check("S3 谱号标注存在", count(svg, "clef") == 1)
check("S4 五线内音无加线（E4/G4）", count(svg, "ledger") == 0, str(count(svg, "ledger")))
check("S4b 中央 C 应有 1 条加线",
      count(st.render_staff2(ev.MSDocument(events=[note(60, 0)]), opts), "ledger") == 1,
      str(count(st.render_staff2(ev.MSDocument(events=[note(60, 0)]), opts), "ledger")))

# ── 加线 ────────────────────────────────────────────────────
high = ev.MSDocument(events=[note(84, 0)])      # C6，远高于五线
svg_high = st.render_staff2(high, opts)
# C6 的 idx=49，五线顶 45 → 需在 47、49 两条加线
check("S5 C6 出现 2 条加线", count(svg_high, "ledger") == 2, str(count(svg_high, "ledger")))

low = ev.MSDocument(events=[note(48, 0)])       # C3，低于高音谱表
svg_low = st.render_staff2(low, opts)
check("S6 低音在高音谱表下出现加线", count(svg_low, "ledger") > 0)

# ── 大谱表 ─────────────────────────────────────────────────
grand = ro.RenderOptions(meter=(4, 4), time_base_us=500_000, clef="grand")
d2 = ev.MSDocument(events=[note(72, 0), note(48, 0)])
svg_g = st.render_staff2(d2, grand)
check("S7 大谱表 10 条线", count(svg_g, "staffline") == 10, str(count(svg_g, "staffline")))
check("S8 大谱表 2 个谱号", count(svg_g, "clef") == 2)
check("S9 大谱表两手各一个符头", count(svg_g, "note") == 2)

# ── 符尾分组 ────────────────────────────────────────────────
# 同拍内两个八分音符 → 应有连杠
pair = ev.MSDocument(events=[note(60, 0, 250_000), note(62, 250_000, 250_000)])
svg_pair = st.render_staff2(pair, opts)
check("S10 同拍两个八分音符 → 有连杠", count(svg_pair, "beam") == 1, str(count(svg_pair, "beam")))

# 跨拍 → 不连杠
across = ev.MSDocument(events=[note(60, 0, 250_000), note(62, 600_000, 250_000)])
svg_across = st.render_staff2(across, opts)
check("S11 跨拍不连杠", count(svg_across, "beam") == 0, str(count(svg_across, "beam")))

# 四分音符（不短于拍）→ 不连杠
quarter = ev.MSDocument(events=[note(60, 0, 500_000), note(62, 0, 500_000)])
check("S12 四分音符不连杠", count(st.render_staff2(quarter, opts), "beam") == 0)

# ── 小节线 ─────────────────────────────────────────────────
four = ev.MSDocument(events=[note(60, i * 500_000, 500_000) for i in range(8)])   # 4s = 2 小节
svg_four = st.render_staff2(four, opts)
check("S13 4s/4-4 → 1 条小节线（不含起点）", count(svg_four, "barline") == 1, str(count(svg_four, "barline")))

noctx = ro.RenderOptions(clef="treble")
svg_no = st.render_staff2(four, noctx)
check("S14 缺语境 → 无小节线且标注", count(svg_no, "barline") == 0 and "无拍号" in svg_no)

# ── 多行系统 ────────────────────────────────────────────────
narrow = ro.RenderOptions(meter=(4, 4), time_base_us=500_000, bars_per_line=1)
long_doc = ev.MSDocument(events=[note(60, i * 500_000, 500_000) for i in range(12)])  # 6s = 3 小节
svg_long = st.render_staff2(long_doc, narrow)
check("S15 bars_per_line=1 → 3 个系统（15 条线）", count(svg_long, "staffline") == 15,
      str(count(svg_long, "staffline")))

# ── 确定性 ─────────────────────────────────────────────────
check("S16 同输入同字节", st.render_staff2(d, opts) == svg)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
