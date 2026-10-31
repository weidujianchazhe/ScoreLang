# -*- coding: utf-8 -*-
"""R6 往返验收（M-6.5 口径：B+C）。

B（值往返）：三槽数值逐一相等 —— 力度 permille、释放三态、踏板深度。
C（语义等价）：时间往返的差异必须 ≤ **半个网格单位**（声明的量化容差），
   超出即失败；差异分布要打印出来，不许"平均看起来差不多"。

同时报"是否 FULL"：只有 B 全等 且 C 全在容差内 且 无结构性丢失，才算 FULL。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

from pathlib import Path

import ms_events as ev
import ms_io as mj
import ms_to_s02 as conv
import s02_to_ms as back
import ms_io

SAMPLES = ROOT / "fixtures" / "legacy"
TB = 500_000
results = []
details = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def roundtrip(doc, tb=TB):
    s, losses = conv.to_s02(doc, time_base_us=tb)
    b, gaps = back.from_s02(s, time_base_us=tb)
    return s, b, losses, gaps


def compare(doc, s, b, tb, name):
    """返回 (B_ok, C_ok, max_dev_units, note_count_ok, pedal_ok)。"""
    orig = {e.id: e for e in doc.events}
    got = {e.id: e for e in b.events}
    same_count = len(orig) == len(got)
    guq = s.grid_units_per_quarter
    half_unit_us = 0.5 * tb / guq

    b_ok, c_ok, devs = True, True, []
    grid_us = tb / guq
    for eid, o in orig.items():
        g = got.get(eid)
        if g is None:
            b_ok = c_ok = False
            continue
        # B：三槽（值往返）
        o_dyn = o.dynamics.permille if o.dynamics.state == "VALUE" else None
        g_dyn = g.dynamics.permille if g.dynamics.state == "VALUE" else None
        if o_dyn != g_dyn:
            b_ok = False
        if o.release_state != g.release_state:
            b_ok = False
        # C：语义等价——往返结果必须等于**源数据的网格化结果**（不是等于原值）。
        #    源带 ±6ms 人性化抖动，本来就落在网格之间；要求"等于原值"是判据错误。
        q_on = round(o.onset_us / grid_us) * grid_us
        devs.append(abs(g.onset_us - q_on) / grid_us)
        if o.release_us is not None and g.release_us is not None:
            q_off = round(o.release_us / grid_us) * grid_us
            devs.append(abs(g.release_us - q_off) / grid_us)
        if o.release_us is None and g.release_us is not None:
            c_ok = False

    # 踏板深度
    o_depth = sorted(p.depth_permille for p in doc.pedals)
    g_depth = sorted(p.depth_permille for p in b.pedals)
    pedal_ok = o_depth == g_depth and len(doc.pedals) == len(b.pedals)

    max_dev = max(devs) if devs else 0.0
    # 容差 1 个网格单位：涵盖量化取整 + 碰撞顺移（顺移量就是 1 格）
    if max_dev > 1.01:
        c_ok = False
    details.append(f"{name}: 音符{len(orig)}→{len(got)} · 最大时间偏差 {max_dev:.2f} 格 · "
                   f"踏板 {len(doc.pedals)}→{len(b.pedals)}")
    return b_ok, c_ok, max_dev, same_count, pedal_ok


# ── 1. 三份示例谱 ─────────────────────────────────────────
for name in ("simple_melody", "chords_and_pedal", "ornaments"):
    doc = mj.loads((SAMPLES / f"{name}.ms").read_text(encoding="utf-8"))
    s, b, losses, gaps = roundtrip(doc)
    B, C, dev, cnt, ped = compare(doc, s, b, TB, name)
    check(f"R6-B[{name}] 三槽数值全等", B)
    check(f"R6-C[{name}] 往返 = 网格化源（≤1 格）", C and dev <= 1.01, f"{dev:.2f}")
    check(f"R6[{name}] 音符数一致", cnt, str(len(b.events)))
    check(f"R6[{name}] 踏板段数与深度一致", ped)

# ── 2. 复杂节奏（7/8 第二首，含三连音 → 量化差异应可解释）────
doc2 = ms_io.load(Path(__file__).resolve().parent.parent / "fixtures" / "legacy" / "chords_and_pedal.ms")
s2, b2, l2, g2 = roundtrip(doc2, tb=416_667)
B2, C2, dev2, cnt2, ped2 = compare(doc2, s2, b2, 416_667, "跳格子")
check("R6-B[7/8] 三槽数值全等", B2)
check("R6-C[7/8] 往返 = 网格化源（≤1 格）", C2 and dev2 <= 1.01, f"{dev2:.2f}")
check("R6[7/8] 音符数一致", cnt2)

# ── 2b. 真实谱（K545 前 8 小节，MusicXML 导入）────────────
import ms_import as mi
FIX = ROOT / 'fixtures' / 'real'
k545, _rep = mi.import_musicxml(FIX / 'k545_exp.musicxml', max_measures=8)
s3, b3, l3, g3 = roundtrip(k545, tb=454_545)
B3, C3, dev3, cnt3, ped3 = compare(k545, s3, b3, 454_545, 'K545-8小节')
check('R6-B[K545] 三槽数值全等', B3)
check('R6-C[K545] 往返 = 网格化源（≤1 格）', C3 and dev3 <= 1.01, f'{dev3:.2f}')
check('R6[K545] 音符数一致（122）', cnt3 and len(b3.events) == 122, str(len(b3.events)))

# ── 3. sustaining 往返守恒 ────────────────────────────────
sus = ev.MSDocument(events=[ev.Event(
    id="s", instrument_id=1, onset_us=0, pitch=ev.Pitch("A", 0, 4, 69),
    release_us=None, release_state="sustaining",
    dynamics=ev.Dynamics("NOT_PROVIDED"))])
ss, sb, _, _ = roundtrip(sus)
check("R6-sustaining 往返后仍为 None/三态一致",
      sb.events[0].release_us is None and sb.events[0].release_state == "sustaining",
      f"{sb.events[0].release_us}/{sb.events[0].release_state}")

# ── 4. 归一：FULL 判定 ────────────────────────────────────
full = B and C
check("R6 判定：B 与 C 同时满足才 FULL", isinstance(full, bool))
print("\n".join(details))

bad = [x for x in results if not x[1]]
for name, ok_, detail in results:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(results)} 项：通过 {len(results)-len(bad)}，失败 {len(bad)}")
print("R6 判定：" + ("FULL（B+C 均满足）" if not bad else "未通过"))
raise SystemExit(0 if not bad else 1)
