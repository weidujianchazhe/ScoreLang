# -*- coding: utf-8 -*-
"""数字简谱渲染测试（II-2）。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re

import ms_events as ev
import ms_render_jianpu as jp
import ms_render as ro
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def note(semi, onset=0, dur=500_000, dyn=1000):
    return ev.Event(id=f"n{semi}_{onset}", instrument_id=1, onset_us=onset,
                    pitch=ev.Pitch(*_spell(semi), semi), release_us=onset + dur,
                    release_state="given",
                    dynamics=ev.Dynamics(ms.VALUE, dyn, "relative_permille", "cal", "notated_inferred"))


def _spell(semi):
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}
    step, alter = base[semi % 12]
    return step, alter, semi // 12 - 1


def doc_of(*notes):
    return ev.MSDocument(events=list(notes))


opts = ro.RenderOptions(meter=(4, 4), time_base_us=500_000)   # 拍长 500ms

# ── 音级映射（C 大调音阶） ─────────────────────────────────
d = doc_of(*[note(s, onset=i * 500_000) for i, s in enumerate([60, 62, 64, 65, 67, 69, 71])])
svg = jp.render_jianpu(d, opts)
check("J1 C 大调音阶 → 1234567", ">1<" in svg.replace('</text>', '<') or "1234567" in re.sub(r'<[^>]+>', '', svg),
      re.sub(r'<[^>]+>', '', svg)[:40])

texts = re.findall(r'class="jp-note"[^>]*>([^<]+)<', svg)
check("J2 七个音各一个音符号", len(texts) == 7, str(texts))
check("J3 音级序列正确", [t.rstrip("—·") for t in texts] == ["1", "2", "3", "4", "5", "6", "7"], str(texts))

# ── 变音 ────────────────────────────────────────────────────
d2 = doc_of(note(61), note(63, onset=500_000))
body2 = re.sub(r'<[^>]+>', '', jp.render_jianpu(d2, opts))
check("J4 C#4 → #1", "#1" in body2, body2[:30])
check("J5 Eb4 → b3", "b3" in body2, body2[:30])

# ── 八度点 ──────────────────────────────────────────────────
d3 = doc_of(note(72))          # C5
svg3 = jp.render_jianpu(d3, opts)
check("J6 C5 出现 1 个高八度点", len(re.findall(r'class="jp-dot"', svg3)) == 1, str(len(re.findall(r'class="jp-dot"', svg3))))

d4 = doc_of(note(48))          # C3
svg4 = jp.render_jianpu(d4, opts)
check("J7 C3 出现 1 个低八度点", len(re.findall(r'class="jp-dot"', svg4)) == 1)

d5 = doc_of(note(60))          # C4（基准）
check("J8 C4 无八度点", len(re.findall(r'class="jp-dot"', jp.render_jianpu(d5, opts))) == 0)

# ── 时值标记 ────────────────────────────────────────────────
d6 = doc_of(note(60, dur=250_000))     # 半拍 → 1 条下划线
check("J9 半拍 → 1 条下划线", len(re.findall(r'class="jp-underline"', jp.render_jianpu(d6, opts))) == 1)

d7 = doc_of(note(60, dur=125_000))     # 四分之一拍 → 2 条
check("J10 1/4 拍 → 2 条下划线", len(re.findall(r'class="jp-underline"', jp.render_jianpu(d7, opts))) == 2)

d8 = doc_of(note(60, dur=1_000_000))   # 两拍 → 延音线
body8 = re.sub(r'<[^>]+>', '', jp.render_jianpu(d8, opts))
check("J11 两拍 → 延音线 —", "—" in body8, body8[:20])

# ── 缺拍号/时基：不猜，只标注 ──────────────────────────────
noctx = ro.RenderOptions()
svg9 = jp.render_jianpu(d, noctx)
check("J12 缺语境 → 标注时值未标注", "时值未标注" in svg9)
check("J13 缺语境 → 不画下划线", len(re.findall(r'class="jp-underline"', svg9)) == 0)

# ── 三种模式 ────────────────────────────────────────────────
mixed = doc_of(note(72), note(48, onset=0))     # 同时刻的高低音
mel = jp.render_jianpu(mixed, opts, mode="melody")
check("J14 melody 模式只画一个音", len(re.findall(r'class="jp-note"', mel)) == 1, str(len(re.findall(r'class="jp-note"', mel))))

two = jp.render_jianpu(mixed, opts, mode="two_hands")
check("J15 two_hands 模式分两行（2 个音符）", len(re.findall(r'class="jp-note"', two)) == 2)

chord = doc_of(note(60), note(64), note(67))
ch = jp.render_jianpu(chord, opts, mode="chords")
body_ch = re.sub(r'<[^>]+>', '', ch)
check("J16 chords 模式括号叠写", "(1 3 5)" in body_ch, body_ch[:30])

try:
    jp.render_jianpu(d, opts, mode="staff")
except ValueError:
    check("J17 未知模式 → 拒绝", True)
else:
    check("J17 未知模式 → 拒绝", False)

# ── 确定性 ─────────────────────────────────────────────────
check("J18 同输入同字节", jp.render_jianpu(d, opts) == svg)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
