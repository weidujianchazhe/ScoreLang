# -*- coding: utf-8 -*-
"""五线规范排版（排表 II-3）。

只依赖 `MSDocument` + `RenderOptions`（拍号/时基/谱号/调号/行宽）。

实现范围（本阶段）：
  ✅ 大谱表（grand：高音 + 低音两行）／单谱表（treble / bass）
  ✅ 加线（ledger lines）：超出五线的音自动补短线
  ✅ 符尾分组（beaming）：同一拍内的短音用连杠代替各自符尾
  ✅ 小节线：需 meter + time_base；缺失时不画（不猜）
  ✅ 多行系统（systems）：按 `bars_per_line` 拆行，避免无限横长
  ✅ 拍号/谱号标注

**明确不做**（并在文档里写明原因）：
  ❌ 符尾的斜度与分组美学、跨行连线、装饰音记号回显

记谱对照：动作与符号的映射在 `render/ms_notation_map.py`（双向表），本文件只负责把它画出来。
"""
from __future__ import annotations

import ms_events as ev
import ms_notation_map as nm

STAFF_STEP = 8.0          # 相邻线间距
LEFT_PAD = 36.0
STAFF_GAP = 56.0          # 大谱表上下行间距
SYSTEM_GAP = 40.0
TOP_PAD = 34.0

_LINE_BASE = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
# 五线位置（diatonic 索引，C4=35）：treble 底线 E4=37，bass 底线 G2=25
STAFF_BOTTOM = {"treble": 37, "bass": 25}
STAFF_SPAN = 8            # 5 条线跨 8 个 diatonic 单位


def _idx(p) -> int:
    return (p.octave + 1) * 7 + _LINE_BASE.get(p.step, 0)


def _clefs(options) -> list:
    if options is not None and options.clef == "grand":
        return ["treble", "bass"]
    if options is not None and options.clef in ("treble", "bass"):
        return [options.clef]
    return ["treble"]


def _systems(doc, options) -> list:
    """按 bars_per_line 拆行；无小节语境则单行。返回 [(start_us, end_us)]。"""
    end = 0
    for e in doc.events:
        end = max(end, e.release_us if e.release_us is not None else e.onset_us)
    bar = options.bar_duration_us() if options is not None else None
    if not bar:
        return [(0, max(end, 1))]
    per = max(1, options.bars_per_line) * bar
    out, t = [], 0
    while t < end:                       # 终点所在系统含在内，不额外产生空系统
        out.append((t, t + per))
        t += per
    return out


def render_staff2(doc: "ev.MSDocument", options=None, warnings: list | None = None) -> str:
    if warnings is not None:
        warnings.extend(ev.check_realization(doc))
    px = options.px_per_sec if options is not None else 120.0
    width = options.line_width_px if options is not None else 1200
    clefs = _clefs(options)
    systems = _systems(doc, options)
    bar = options.bar_duration_us() if options is not None else None

    staff_heights = len(clefs) * STAFF_SPAN * (STAFF_STEP / 2)
    system_h = staff_heights + (len(clefs) - 1) * (STAFF_GAP - STAFF_SPAN * STAFF_STEP / 2) + SYSTEM_GAP
    height = TOP_PAD + system_h * len(systems) + 20

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + LEFT_PAD:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width + LEFT_PAD:.0f} {height:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']

    if options is not None and options.label_missing_context and bar is None:
        out.append(f'<text class="no-meter" x="{LEFT_PAD:.0f}" y="14" font-size="10" fill="#999">'
                   f'无拍号/时基：不画小节线 | {options.describe()}</text>')

    # 音乐终点只需算一次（此前写在小节线区块内，会随系统数重复遍历 → 平方级）
    music_end = 0
    for e in doc.events:
        music_end = max(music_end, e.release_us if e.release_us is not None else e.onset_us)

    # 按系统预分桶：避免"每个系统都遍历全部事件"导致的平方级开销
    turn_of = {t.event_id: t for t in getattr(doc, "turns", [])}
    buckets = [[] for _ in systems]
    if systems:
        per = systems[0][1] - systems[0][0]
        base = systems[0][0]
        for e in doc.events:
            i = int((e.onset_us - base) // per) if per > 0 else 0
            i = max(0, min(len(systems) - 1, i))
            buckets[i].append(e)

    for si, (sys_start, sys_end) in enumerate(systems):
        span_us = max(1, sys_end - sys_start)
        scale = width / (span_us / 1_000_000 * px) if px else 1.0
        base_y = TOP_PAD + si * system_h
        for ci, clef in enumerate(clefs):
            top_y = base_y + ci * (STAFF_GAP + 3 * STAFF_STEP)
            bottom_idx = STAFF_BOTTOM[clef]
            bottom_y = top_y + STAFF_SPAN * (STAFF_STEP / 2)

            for i in range(5):
                y = bottom_y - i * STAFF_STEP
                out.append(f'<line class="staffline" x1="{LEFT_PAD:.1f}" y1="{y:.1f}" '
                           f'x2="{LEFT_PAD + width:.1f}" y2="{y:.1f}" stroke="#333" stroke-width="0.7"/>')
            out.append(f'<text class="clef" x="4" y="{bottom_y - 2:.1f}" font-size="16" fill="#333">'
                       f'{"𝄞" if clef == "treble" else "𝄢"}</text>')

            sel = [e for e in buckets[si]
                   if sys_start <= e.onset_us < sys_end
                   and ((clef == "treble" and e.pitch.semitone >= 60)
                        or (clef == "bass" and e.pitch.semitone < 60)
                        or len(clefs) == 1)]
            xs = {}
            for e in sel:
                x = LEFT_PAD + ((e.onset_us - sys_start) / 1_000_000) * px * scale
                xs[e.id] = x
                idx = _idx(e.pitch)
                y = bottom_y - (idx - bottom_idx) * (STAFF_STEP / 2)
                dur = (e.release_us - e.onset_us) if e.release_us else 0
                filled = dur < 600_000        # 短音实心、长音空心（简化）
                out.append(f'<ellipse class="note" data-id="{e.id}" cx="{x:.1f}" cy="{y:.1f}" '
                           f'rx="3.6" ry="2.7" fill="{"#111" if filled else "#fff"}" '
                           f'stroke="#111" stroke-width="0.9"/>')
                # 符干：中线以下朝上，以上朝下
                up = (idx - bottom_idx) < STAFF_SPAN / 1
                sy1, sy2 = (y, y - 3.2 * STAFF_STEP) if up else (y, y + 3.2 * STAFF_STEP)
                out.append(f'<line class="stem" x1="{x + (3.2 if up else -3.2):.1f}" y1="{sy1:.1f}" '
                           f'x2="{x + (3.2 if up else -3.2):.1f}" y2="{sy2:.1f}" stroke="#111" stroke-width="0.8"/>')

                # 加线：超出五线范围时，按**线位**补（隔一个 diatonic 单位一条）
                if idx > bottom_idx + STAFF_SPAN:
                    for L in range(bottom_idx + STAFF_SPAN + 2, idx + 1, 2):
                        ly = bottom_y - (L - bottom_idx) * (STAFF_STEP / 2)
                        out.append(f'<line class="ledger" x1="{x - 5:.1f}" y1="{ly:.1f}" '
                                   f'x2="{x + 5:.1f}" y2="{ly:.1f}" stroke="#111" stroke-width="0.8"/>')
                elif idx < bottom_idx:
                    for L in range(bottom_idx - 2, idx - 1, -2):
                        ly = bottom_y - (L - bottom_idx) * (STAFF_STEP / 2)
                        out.append(f'<line class="ledger" x1="{x - 5:.1f}" y1="{ly:.1f}" '
                                   f'x2="{x + 5:.1f}" y2="{ly:.1f}" stroke="#111" stroke-width="0.8"/>')

            # 动作记号（对照表见 ms_notation_map）：画在音符上方
            for e in sel:
                t = turn_of.get(e.id)
                if t is None:
                    continue
                glyph, place, _cat = nm.symbol_for(t.kind)
                if not glyph:
                    continue
                x = xs.get(e.id)
                idx = _idx(e.pitch)
                y = bottom_y - (idx - bottom_idx) * (STAFF_STEP / 2)
                ty = y - 9 if place == "above" else y + 14
                out.append(f'<text class="turn turn-{t.kind}" data-id="{e.id}" '
                           f'x="{x:.1f}" y="{ty:.1f}" font-size="7" fill="#333" '
                           f'text-anchor="middle">{glyph}</text>')
            # 连音/延音弧：由相邻关系推出（不是字段）
            for arc_kind, id_a, id_b in nm.arcs_for(sel, doc.turns):
                x1, x2 = xs.get(id_a), xs.get(id_b)
                if x1 is None or x2 is None or x2 - x1 < 6:
                    continue
                ya = bottom_y - (_idx(next(e for e in sel if e.id == id_a).pitch) - bottom_idx) * (STAFF_STEP / 2)
                yb = bottom_y - (_idx(next(e for e in sel if e.id == id_b).pitch) - bottom_idx) * (STAFF_STEP / 2)
                top = min(ya, yb) - 7
                out.append(f'<path class="{arc_kind}" data-a="{id_a}" data-b="{id_b}" '
                           f'd="M {x1 + 3:.1f} {ya - 3:.1f} Q {(x1 + x2) / 2:.1f} {top:.1f} '
                           f'{x2 - 3:.1f} {yb - 3:.1f}" fill="none" stroke="#333" stroke-width="0.8"/>')

            # 符尾分组：同一拍内、时值短于拍的音连杠
            beat = options.beat_duration_us() if options is not None else None
            if beat and sel:
                groups = {}
                for e in sel:
                    dur = (e.release_us - e.onset_us) if e.release_us else 0
                    if dur < beat:
                        groups.setdefault(e.onset_us // beat, []).append(e)
                for _, members in groups.items():
                    if len(members) < 2:
                        continue
                    ys = []
                    for e in members:
                        idx = _idx(e.pitch)
                        y = bottom_y - (idx - bottom_idx) * (STAFF_STEP / 2)
                        up = (idx - bottom_idx) < STAFF_SPAN
                        ys.append(y - 3.2 * STAFF_STEP if up else y + 3.2 * STAFF_STEP)
                    x1, x2 = xs[members[0].id] + 3.2, xs[members[-1].id] + 3.2
                    ym = sum(ys) / len(ys)
                    out.append(f'<line class="beam" x1="{x1:.1f}" y1="{ym:.1f}" '
                               f'x2="{x2:.1f}" y2="{ym:.1f}" stroke="#111" stroke-width="2.4"/>')

        # 小节线（仅当有语境），且不超出实际音乐终点
        if bar:
            t = (int(sys_start // bar) + 1) * bar
            while t < min(sys_end, music_end):
                x = LEFT_PAD + ((t - sys_start) / 1_000_000) * px * scale
                out.append(f'<line class="barline" x1="{x:.1f}" y1="{base_y:.1f}" '
                           f'x2="{x:.1f}" y2="{base_y + staff_heights:.1f}" stroke="#444" stroke-width="0.9"/>')
                t += bar

    out.append("</svg>")
    return "\n".join(out)
