# -*- coding: utf-8 -*-
"""引擎呈现层阶段 1 测试：渲染 SVG + 听觉参数。"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import re

import ms_audio as au
import ms_events as ev
import ms_render as rd
import ms_semantics as ms

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def doc1():
    return ev.MSDocument(
        piano_count=1, constraint_mode="single_piano",
        events=[
            ev.Event(id="a", instrument_id=1, onset_us=0,
                     pitch=ev.Pitch("C", 0, 4, 60), release_us=500_000, release_state="given",
                     dynamics=ev.Dynamics(ms.VALUE, 1000, "relative_permille", "cal", "measured")),
            ev.Event(id="b", instrument_id=1, onset_us=1_000_000,
                     pitch=ev.Pitch("G", 0, 4, 67), release_us=None, release_state="sustaining",
                     dynamics=ev.Dynamics(ms.NOT_PROVIDED)),
        ],
        pedals=[ev.PedalSegment(1, "sustain", 0, 2_000_000, 1000),
                ev.PedalSegment(1, "sostenuto", 500_000, 1_500_000, 400)],
    )


# ── 事件图形谱 ───────────────────────────────────────────────
svg = rd.render_pianoroll(doc1())
check("R1 是 svg", svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
check("R2 事件图元数=2", len(re.findall(r'class="note"', svg)) == 2, str(len(re.findall(r'class="note"', svg))))
check("R3 踏板轨含两个 kind", "sustain" in svg and "sostenuto" in svg)
check("R4 sustaining 用虚线（不伪造长度）", 'stroke-dasharray' in svg)
check("R5 确定性（同输入同字节）", rd.render_pianoroll(doc1()) == svg)
check("R6 无随机 id，图元带 data-id", 'data-id="a"' in svg and 'data-id="b"' in svg)

# 时间映射：onset 1.0s 应比 0s 更靠右（用 x 坐标粗验）
xs = [float(m) for m in re.findall(r'class="note" data-id="[ab]" x="([\d.]+)"', svg)]
check("R7 时间越晚 x 越大", len(xs) == 2 and xs[1] > xs[0], str(xs))

# ── 简化五线谱 ───────────────────────────────────────────────
staff = rd.render_staff(doc1())
check("S1 五线存在", len(re.findall(r'class="staffline"', staff)) == 5)
check("S2 符头数=2", len(re.findall(r'class="note"', staff)) == 2)
check("S3 符干存在", len(re.findall(r'class="stem"', staff)) == 2)
check("S4 高音在低音之上（G4 的 y 小于 C4）",
      float(re.search(r'data-id="b" cx="[\d.]+" cy="([\d.]+)"', staff).group(1))
      < float(re.search(r'data-id="a" cx="[\d.]+" cy="([\d.]+)"', staff).group(1)))

# ── 文本摘要 ─────────────────────────────────────────────────
txt = rd.render_text(doc1())
check("T1 文本含事件与踏板", "a: key=60" in txt and "sustain" in txt)

# ── 听觉参数 ─────────────────────────────────────────────────
check("A1 A4=440Hz", abs(au.frequency_hz(69) - 440.0) < 1e-9)
check("A2 C4≈261.626Hz", abs(au.frequency_hz(60) - 261.626) < 0.01, str(au.frequency_hz(60)))
check("A3 中性 f(1000)=1.0", abs(au.default_calibration(1000) - 1.0) < 1e-12)
check("A4 标定单调", all(au.default_calibration(p) <= au.default_calibration(q)
                         for p, q in zip([100, 500, 1000, 2000], [500, 1000, 2000, 4000])))

params = au.event_parameters(doc1())
p0, p1 = params[0], params[1]
check("A5 两事件都出参数", len(params) == 2)
check("A6 中性力度振幅=1.0", abs(p0["amplitude"] - 1.0) < 1e-12)
check("A7 NOT_PROVIDED 按中性算但留痕",
      abs(p1["amplitude"] - 1.0) < 1e-12 and p1["dynamics_state"] == ms.NOT_PROVIDED
      and p1["dynamics_permille"] is None)
check("A8 sustaining 的 duration 为 None", p1["duration_us"] is None)
check("A9 有 release 的 duration 正确", p0["duration_us"] == 500_000)


def bad_cal(x):
    return 1.0


def non_monotone(x):
    return 1.0 if x == 1000 else 0.5


def try_cal(fn, name):
    try:
        au.event_parameters(doc1(), fn)
    except ValueError as e:
        check(name, True, str(e)[:40])
    else:
        check(name, False, "应当拒绝")


try_cal(non_monotone, "A10 非单调标定 → 拒绝")


def wrong_neutral(x):
    return x / 999.0


try_cal(wrong_neutral, "A11 f(1000)≠1.0 → 拒绝")

tracks = au.pedal_track_parameters(doc1())
check("A12 踏板轨按 (piano,kind) 分组", set(tracks) == {"1:sustain", "1:sostenuto"}, str(set(tracks)))
check("A13 深度归一化", abs(tracks["1:sostenuto"][0]["depth"] - 0.4) < 1e-9)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
raise SystemExit(0 if not bad else 1)
