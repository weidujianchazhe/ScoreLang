# -*- coding: utf-8 -*-
"""完整五线谱渲染测试（结构级：我不能看图，只能核对结构与数量）。"""
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
import ms_score as sc
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def pitch(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return ev.Pitch(step, alter, semi // 12 - 1, semi)


def note(semi, onset, dur=500_000, permille=1000):
    return ev.Event(id=f"e{semi}_{onset}", instrument_id=1, onset_us=onset, pitch=pitch(semi),
                    release_us=onset + dur, release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, permille, "relative_permille", "c", "measured"))


TB = 500_000
OPTS = ro.RenderOptions(meter=(4, 4), time_base_us=TB, clef="grand",
                        bars_per_line=4, line_width_px=1100)


def count(svg, pattern):
    return len(re.findall(pattern, svg))


# ── 基本 ────────────────────────────────────────────────────
d = ev.MSDocument(events=[note(60, 0), note(72, 500_000), note(48, 1_000_000), note(76, 1_500_000)])
svg = sc.render_score(d, OPTS, title="T")
check("S1 符头数 = 事件数", count(svg, "<ellipse") == 4, str(count(svg, "<ellipse")))
check("S2 大谱表有两个谱号字形", "𝄞" in svg and "𝄢" in svg)
check("S3 有拍号 4/4", svg.count(">4<") >= 2, str(svg.count(">4<")))
check("S4 五条谱线（每行）", count(svg, 'stroke-width="0.7"') == 10,
      str(count(svg, 'stroke-width="0.7"')))
check("S5 标题出现", ">T<" in svg)

# ── 临时记号 ───────────────────────────────────────────────
gsharp = ev.MSDocument(events=[ev.Event(id="g", instrument_id=1, onset_us=0,
                                        pitch=ev.Pitch("G", 1, 4, 68),
                                        release_us=500_000, release_state="given")])
svg_g = sc.render_score(gsharp, OPTS, title="")
check("S6 G♯ 有升号", ">#<" in svg_g)

# 同小节先 # 后还原 → 需要还原号
nat = ev.MSDocument(events=[
    ev.Event(id="g1", instrument_id=1, onset_us=0, pitch=ev.Pitch("G", 1, 4, 68),
             release_us=500_000, release_state="given"),
    ev.Event(id="g2", instrument_id=1, onset_us=500_000, pitch=ev.Pitch("G", 0, 4, 67),
             release_us=1_000_000, release_state="given")])
svg_n = sc.render_score(nat, OPTS, title="")
check("S7 同小节 G♯→G 出现还原号", ">n<" in svg_n)

# ── 休止符 ────────────────────────────────────────────────
gappy = ev.MSDocument(events=[note(72, 2_000_000, 500_000)])   # 前 4 拍空
svg_r = sc.render_score(gappy, OPTS, title="")
check("S8 空拍处产生休止符", ("<rect" in svg_r) or ("l 4 4" in svg_r))

# ── 节奏符号 ──────────────────────────────────────────────
rhythm = ev.MSDocument(events=[note(72, 0, 2_000_000), note(74, 2_000_000, 1_500_000)])
svg_ry = sc.render_score(rhythm, OPTS, title="")
check("S9 二分音符空心（有白色填充）", "#fff" in svg_ry)
check("S10 附点存在", "<circle" in svg_ry)

# ── 力度（按小节判定：两小节 p → f）─────────────────────────
dyn = ev.MSDocument(events=[note(72, 0, 500_000, 700), note(72, 2_000_000, 500_000, 1500)])
svg_d = sc.render_score(dyn, OPTS, title="")
check("S11 力度记号 p 与 f 都出现（跨小节变化）", ">p<" in svg_d and ">f<" in svg_d)

# ── 踏板 ──────────────────────────────────────────────────
ped = ev.MSDocument(events=[note(48, 0, 2_000_000)],
                    pedals=[ev.PedalSegment(1, "sustain", 0, 1_000_000, 1000)])
svg_p = sc.render_score(ped, OPTS, title="")
check("S12 踏板记号 Ped. 与 *", ">Ped.<" in svg_p and ">*<" in svg_p)

# ── 分页 ──────────────────────────────────────────────────
many = ev.MSDocument(events=[note(72, i * TB, TB) for i in range(4 * 20)])   # 20 小节
svg_m = sc.render_score(many, OPTS, title="")
check("S13 20 小节 → 5 个系统 / 2 页", "1 / 2" in svg_m and "2 / 2" in svg_m, "分页标记缺失")

# ── 单谱表 ────────────────────────────────────────────────
solo = ro.RenderOptions(meter=(4, 4), time_base_us=TB, clef="treble",
                        bars_per_line=4, line_width_px=1100)
svg_s = sc.render_score(ev.MSDocument(events=[note(72, 0)]), solo, title="")
check("S14 单谱表只有 5 条线", count(svg_s, 'stroke-width="0.7"') == 5,
      str(count(svg_s, 'stroke-width="0.7"')))

# ── 确定性 ────────────────────────────────────────────────
check("S15 同输入同字节", sc.render_score(d, OPTS, title="T") == svg)

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
