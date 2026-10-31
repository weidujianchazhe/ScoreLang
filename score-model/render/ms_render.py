# -*- coding: utf-8 -*-
"""呈现层：MSDocument → SVG。"""
from __future__ import annotations

import math

import ms_events as ev

# ── 默认样式常量（可被调用方覆盖，但必须显式传入） ─────────────
PX_PER_SEC = 120.0
ROW_PX = 6.0           # 每个半音的行高（事件谱）
LEFT_PAD = 40.0
TOP_PAD = 20.0
LANE_H = 18.0          # 每条踏板轨高度
STAFF_STEP = 8.0       # 五线谱：相邻音级间距


def _scale(doc: "ev.MSDocument", px_per_sec: float):
    total_us = 0
    for e in doc.events:
        total_us = max(total_us, e.release_us if e.release_us is not None else e.onset_us)
    for p in doc.pedals:
        total_us = max(total_us, p.end_us if p.end_us is not None else p.start_us)
    seconds = total_us / 1_000_000
    return seconds, max(1.0, seconds * px_per_sec)


def render_pianoroll(doc: "ev.MSDocument", px_per_sec: float = PX_PER_SEC,
                     warnings: list | None = None,
                     row_px: float = ROW_PX, options=None) -> str:
    """事件图形谱：时间轴 + 键盘纵向 + 力度透明度 + 三条踏板轨。

    `options`（`RenderOptions`）：给出 meter + time_base 时画小节线；否则不画（不猜）。
    `warnings`：给出时收集**演奏收束**问题（`check_realization`），不改画面。
    """
    if warnings is not None:
        warnings.extend(ev.check_realization(doc))
    if options is not None:
        px_per_sec = options.px_per_sec
    seconds, width = _scale(doc, px_per_sec)
    key_span = ev.KEY_MAX - ev.KEY_MIN + 1
    roll_h = key_span * row_px
    lanes = _pedal_lanes(doc)
    height = TOP_PAD + roll_h + LANE_H * len(lanes) + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + LEFT_PAD:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width + LEFT_PAD:.0f} {height:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']

    # 键盘背景：C 键加浅色行，便于对齐
    for k in range(ev.KEY_MIN, ev.KEY_MAX + 1):
        y = TOP_PAD + (ev.KEY_MAX - k) * row_px
        if k % 12 == 0:
            out.append(f'<rect x="{LEFT_PAD}" y="{y:.1f}" width="{width:.1f}" '
                       f'height="{row_px:.1f}" fill="#f2f2f2"/>')

    # 事件
    for e in doc.events:
        x = LEFT_PAD + (e.onset_us / 1_000_000) * px_per_sec
        if e.release_us is None:
            w = px_per_sec * 0.25          # sustaining：短开口块，不伪造长度
            closed = False
        else:
            w = max(1.0, ((e.release_us - e.onset_us) / 1_000_000) * px_per_sec)
            closed = True
        y = TOP_PAD + (ev.KEY_MAX - e.key()) * row_px
        alpha = _alpha(e)
        shape = "" if closed else ' stroke-dasharray="3,2"'
        out.append(f'<rect class="note" data-id="{e.id}" x="{x:.1f}" y="{y:.1f}" '
                   f'width="{w:.1f}" height="{row_px - 1:.1f}" fill="#2b6cb0" '
                   f'fill-opacity="{alpha:.2f}"{shape}/>')

    # 踏板轨
    base_y = TOP_PAD + roll_h
    for i, kind in enumerate(lanes):
        y0 = base_y + i * LANE_H
        out.append(f'<line x1="{LEFT_PAD}" y1="{y0:.1f}" x2="{LEFT_PAD + width:.1f}" '
                   f'y2="{y0:.1f}" stroke="#999" stroke-width="0.5"/>')
        out.append(f'<text x="2" y="{y0 + LANE_H - 5:.1f}" font-size="9" fill="#555">{kind}</text>')
        for p in doc.pedals:
            if p.kind != kind:
                continue
            x = LEFT_PAD + (p.start_us / 1_000_000) * px_per_sec
            if p.end_us is None:
                w = px_per_sec * 0.25
            else:
                w = max(1.0, ((p.end_us - p.start_us) / 1_000_000) * px_per_sec)
            h = (p.depth_permille / 1000.0) * (LANE_H - 6)
            out.append(f'<rect class="pedal" data-kind="{kind}" x="{x:.1f}" '
                       f'y="{y0 + LANE_H - 2 - h:.1f}" width="{w:.1f}" height="{h:.1f}" '
                       f'fill="#b7791f" fill-opacity="0.55"/>')

    out.extend(_bar_lines(doc, options, px_per_sec, roll_h, TOP_PAD))
    out.append("</svg>")
    return "\n".join(out)


def _max_end_us(doc) -> int:
    end = 0
    for e in doc.events:
        end = max(end, e.release_us if e.release_us is not None else e.onset_us)
    for p in doc.pedals:
        end = max(end, p.end_us if p.end_us is not None else p.start_us)
    return end


def _bar_lines(doc, options, px_per_sec: float, height: float, y0: float) -> list:
    """按 `options` 画小节线；无语境时不猜，只按需标注。"""
    if options is None:
        return []
    starts = options.bar_starts_us(_max_end_us(doc))
    if starts:
        lines = []
        for t in starts:
            x = LEFT_PAD + (t / 1_000_000) * px_per_sec
            lines.append(f'<line class="barline" x1="{x:.1f}" y1="{y0:.1f}" '
                         f'x2="{x:.1f}" y2="{y0 + height:.1f}" stroke="#444" stroke-width="0.9"/>')
        return lines
    if options.label_missing_context:
        return [f'<text class="no-meter" x="{LEFT_PAD + 4:.1f}" y="{max(8.0, y0 - 6):.1f}" '
                f'font-size="9" fill="#999">无拍号/时基：不画小节线 | {options.describe()}</text>']
    return []


def _alpha(e) -> float:
    """力度 → 不透明度（视觉编码）。NOT_PROVIDED 用固定值，但事件语义不变。"""
    d = e.dynamics
    if d.state != "VALUE" or d.permille is None:
        return 0.45                        # 未提供：中等灰，不冒充"中性"
    return max(0.15, min(1.0, 0.15 + 0.85 * (d.permille / 2000.0)))


def _pedal_lanes(doc) -> list:
    kinds = []
    for p in doc.pedals:
        if p.kind not in kinds:
            kinds.append(p.kind)
    return kinds


# ── 真谱渲染（钢琴大谱表/单谱表） ───────────────────────────────
SPACE = 8.0                 # 线间距（1 个音级 = SPACE/2）
STAFF_H = 4 * SPACE
LEFT = 96.0
SYS_GAP = 58.0              # 大谱表两行间距（含中间加线空间）


def _bar_us_of(options) -> int:
    if options is not None and options.bar_duration_us():
        return int(options.bar_duration_us())
    return 4 * 500_000


def _content_us(doc) -> int:
    vals = [int(e.release_us or e.onset_us) for e in doc.events]
    return max(vals + [int(getattr(doc, "trailing_silence_us", 0) or 0)])


# 音级（C=0..B=6 + 7*octave）；各谱表最底线音级
_TREBLE_BOTTOM = 2 + 7 * 4      # E4
_BASS_BOTTOM = 4 + 7 * 2        # G2
_STEP_TYPE = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}


def _diatonic(p) -> int:
    return _STEP_TYPE.get(p.step, 0) + 7 * int(p.octave)


def _pos(p, clef: str) -> int:
    """相对本谱表底线的半格数（0 = 底线，2 = 第一间…8 = 顶线）。"""
    base = _TREBLE_BOTTOM if clef == "treble" else _BASS_BOTTOM
    return (_diatonic(p) - base) * 2


def _acc(p) -> str:
    a = int(p.alter)
    if a == 0:
        return ""
    if a > 0:
        return "\u266f" * a
    return "\u266d" * (-a)


# 调号位置（半格数，从底线算）：升号 F C G D A E B / 降号 B E A D G C F
_SHARP_POS = {"treble": [8, 5, 9, 6, 3, 7, 4], "bass": [6, 3, 7, 4, 1, 5, 2]}
_FLAT_POS = {"treble": [4, 7, 3, 6, 2, 5, 1], "bass": [2, 5, 1, 4, 0, 3, -1]}


def _clean(doc):
    return sorted([e for e in doc.events], key=lambda e: (e.onset_us, e.id))


# ── 调号估算（Krumhansl 大调模板相关） ────────────────────────
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52,
                  5.19, 2.39, 3.66, 2.29, 2.88]   # C 大调
_SHARP_STEPS = {"F": 1, "C": 2, "G": 4, "D": 1, "A": 3, "E": 5, "B": 6}
# 各调号对应的升/降音级（按 FIFTHS 顺序）
_SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
_FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]


def estimate_key_sig(doc) -> int:
    """从音高分布估调号（-7..7，正=升号数）。只用于渲染，不改模型。"""
    import math as _m
    pc = [0.0] * 12
    for e in getattr(doc, "events", []):
        dur = max(1, int(e.release_us or e.onset_us) - int(e.onset_us))
        pc[int(e.pitch.semitone) % 12] += dur
    if sum(pc) <= 0:
        return 0
    best, best_r = 0, -9e9
    for fifths in range(-7, 8):
        # 该调的主音（大调）：C 0, G 7, D 2, A 9, E 4, B 11, F# 6, C# 1, F 5, Bb 10...
        tonic = (fifths * 7) % 12
        prof = [0.0] * 12
        for i, v in enumerate(_MAJOR_PROFILE):
            prof[(tonic + i) % 12] = v
        num = sum(a * b for a, b in zip(pc, prof))
        den = (_m.sqrt(sum(a * a for a in pc)) *
               _m.sqrt(sum(b * b for b in prof))) or 1.0
        r = num / den
        if r > best_r:
            best, best_r = fifths, r
    return int(best)


def _key_acc_map(key_sig: int) -> dict:
    """调号本身要求的音级变化：{step: alter}。"""
    m = {}
    if key_sig > 0:
        for s in _SHARP_ORDER[:key_sig]:
            m[s] = 1
    elif key_sig < 0:
        for s in _FLAT_ORDER[:abs(key_sig)]:
            m[s] = -1
    return m


def _bar_us_of(options) -> int:
    if options is not None and options.bar_duration_us():
        return int(options.bar_duration_us())
    return 4 * 500_000


def _content_us(doc) -> int:
    vals = [int(e.release_us or e.onset_us) for e in doc.events]
    return max(vals + [int(getattr(doc, "trailing_silence_us", 0) or 0)])


_TREBLE_BOTTOM = 2 + 7 * 4
_BASS_BOTTOM = 4 + 7 * 2
_STEP_TYPE = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_SHARP_POS = {"treble": [8, 5, 9, 6, 3, 7, 4], "bass": [6, 3, 7, 4, 1, 5, 2]}
_FLAT_POS = {"treble": [4, 7, 3, 6, 2, 5, 1], "bass": [2, 5, 1, 4, 0, 3, -1]}
_PERC_POS = {35: 1, 36: 1, 37: 4, 38: 3, 39: 3, 40: 3,
             41: 2, 42: 6, 43: 2, 44: 6, 45: 4, 46: 6,
             47: 5, 48: 6, 49: 6, 50: 5, 51: 6, 52: 6, 53: 6}


def _diatonic(p) -> int:
    return _STEP_TYPE.get(p.step, 0) + 7 * int(p.octave)


_FLAT_NAMES = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
               ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)]
_SHARP_NAMES = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
                ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]


def _spell(p, key_sig: int):
    """显示层等音拼写：降号调用降号名，升号调用升号名（模型可能把 D♭ 存成 C♯）。"""
    idx = int(p.semitone) % 12
    flat = key_sig < 0 or (key_sig == 0 and int(p.alter) < 0)
    step, alter = (_FLAT_NAMES if flat else _SHARP_NAMES)[idx]
    octave = int(p.semitone) // 12 - 1
    return step, alter, octave


def _pos_do(step: str, octave: int, clef: str) -> int:
    base = _TREBLE_BOTTOM if clef == "treble" else _BASS_BOTTOM
    idx = _STEP_TYPE.get(step, 0) + 7 * int(octave)
    return (idx - base) * 2


def _pos(p, clef: str) -> int:
    if clef == "percussion":
        return _PERC_POS.get(int(p.semitone), 3) * 2
    base = _TREBLE_BOTTOM if clef == "treble" else _BASS_BOTTOM
    return (_diatonic(p) - base) * 2


def _acc_from(alter: int, step: str, key_map: dict) -> str:
    a = int(alter)
    want = int(key_map.get(step, 0))
    if a == want:
        return ""
    diff = a - want
    if diff == 0:
        return ""
    if diff > 0:
        return "\u266f" * diff if want == 0 else "\u266e"
    return "\u266d" * (-diff) if want == 0 else "\u266e"


def _clean(doc):
    return sorted([e for e in doc.events], key=lambda e: (e.onset_us, e.id))


def render_staff(doc: "ev.MSDocument", px_per_sec: float = PX_PER_SEC, options=None,
                 warnings: list | None = None) -> str:
    """真谱：钢琴大谱表 / 单谱表（谱号·调号·拍号·临时记号·加线·符杠·休止·小节线）。"""
    if warnings is not None:
        warnings.extend(ev.check_realization(doc))
    if options is not None and options.px_per_sec:
        px_per_sec = options.px_per_sec
    meter = (options.meter if options and options.meter else (4, 4))
    clef = (options.clef if options and options.clef else "treble")
    key_sig = (options.key_sig if options and options.key_sig is not None
               else estimate_key_sig(doc))
    key_map = _key_acc_map(int(key_sig))
    no_meter = (options is None or options.meter is None
                or options.time_base_us is None)
    bar_us = _bar_us_of(options)
    total_us = _content_us(doc)
    nbars = 1 if no_meter else max(1, int(math.ceil(total_us / bar_us)))
    beats = int(meter[0])
    bar_w = max(180.0, 55.0 * beats) * (max(1, int(math.ceil(total_us / 500_000 / beats)))
                                         if no_meter else 1)
    width = LEFT + nbars * bar_w + 16
    staves = ["treble", "bass"] if clef == "grand" else [clef]
    sys_h = len(staves) * STAFF_H + (SYS_GAP if len(staves) > 1 else 0)
    height = 34 + sys_h + 52
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           '<g font-family="Times New Roman, Segoe UI Symbol, serif" fill="#111">']
    top_y = 34.0
    if no_meter:
        out.append(f'<text x="{LEFT - 58:.1f}" y="{top_y - 14:.1f}" '
                   f'font-size="11" fill="#a00">无拍号（未给 meter）：不画小节线</text>')
    ys = {}
    for i, name in enumerate(staves):
        y0 = top_y + i * (STAFF_H + SYS_GAP)
        ys[name] = y0
        for k in range(5):
            yy = y0 + k * SPACE
            out.append(f'<line class="staffline" x1="{LEFT - 58:.1f}" y1="{yy:.1f}" '
                       f'x2="{width - 12:.1f}" y2="{yy:.1f}" stroke="#222" stroke-width="0.8"/>')
        if name == "percussion":
            out.append(f'<line x1="{LEFT - 44:.1f}" y1="{y0:.1f}" x2="{LEFT - 44:.1f}" '
                       f'y2="{y0 + STAFF_H:.1f}" stroke="#222" stroke-width="2.4"/>')
            out.append(f'<line x1="{LEFT - 40:.1f}" y1="{y0:.1f}" x2="{LEFT - 40:.1f}" '
                       f'y2="{y0 + STAFF_H:.1f}" stroke="#222" stroke-width="1.2"/>')
        else:
            glyph = "\U0001D11E" if name == "treble" else "\U0001D122"
            out.append(f'<text x="{LEFT - 56:.1f}" y="{y0 + STAFF_H * 0.86:.1f}" '
                       f'font-size="{STAFF_H * 2.2:.1f}">{glyph}</text>')
            if key_sig:
                pos = (_SHARP_POS if key_sig > 0 else _FLAT_POS)[name]
                sym = "\u266f" if key_sig > 0 else "\u266d"
                for j in range(abs(int(key_sig))):
                    xx = LEFT - 30 + j * 9.5
                    yy = y0 + (STAFF_H - pos[j] * SPACE / 2)
                    out.append(f'<text x="{xx:.1f}" y="{yy:.1f}" '
                               f'font-size="{SPACE * 1.6:.1f}">{sym}</text>')
        out.append(f'<text x="{LEFT - 12:.1f}" y="{y0 + SPACE * 1.35:.1f}" '
                   f'font-size="{SPACE * 1.5:.1f}" font-weight="600">{beats}</text>')
        out.append(f'<text x="{LEFT - 12:.1f}" y="{y0 + SPACE * 3.1:.1f}" '
                   f'font-size="{SPACE * 1.5:.1f}" font-weight="600">{meter[1]}</text>')
    for b in range(nbars + 1):
        x = LEFT + b * bar_w
        if no_meter and b > 0:
            continue
        cls = ' class="barline"' if (not no_meter and b < nbars) else ""
        for name in staves:
            y0 = ys[name]
            out.append(f'<line{cls} x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" '
                       f'y2="{y0 + STAFF_H:.1f}" stroke="#222" '
                       f'stroke-width="{1.4 if b in (0, nbars) else 0.9}"/>')
        if b < nbars:
            out.append(f'<text x="{x + 3:.1f}" y="{top_y - 12:.1f}" font-size="10" '
                       f'fill="#666">{b + 1}</text>')

    # 音符：先收集，再画（符杠需要分组）
    groups = {}   # (bar, staff, up) -> [(x, sy, dur_q, x_stem)]
    acc_shown = {}
    drawn = {"treble": set(), "bass": set(), "percussion": set()}
    for e in _clean(doc):
        name = ("treble" if e.pitch.semitone >= 60 else "bass") \
            if clef == "grand" else clef
        step, alter, octave = _spell(e.pitch, int(key_sig))
        y0 = ys[name]
        pos = _pos(e.pitch, name) if name == "percussion" \
            else _pos_do(step, octave, name)
        x = LEFT + (e.onset_us / bar_us) * bar_w
        y = y0 + STAFF_H - pos * (SPACE / 2)
        bar_idx = int(e.onset_us // bar_us)
        drawn.setdefault(name, set()).add(bar_idx)
        if pos < 0:
            p0 = 0
            while p0 >= pos:
                yy = y0 + STAFF_H - p0 * (SPACE / 2)
                out.append(f'<line x1="{x - 10:.1f}" y1="{yy:.1f}" x2="{x + 10:.1f}" '
                           f'y2="{yy:.1f}" stroke="#222" stroke-width="0.8"/>')
                p0 -= 2
        elif pos > 8:
            p0 = 10
            while p0 <= pos:
                yy = y0 + STAFF_H - p0 * (SPACE / 2)
                out.append(f'<line x1="{x - 10:.1f}" y1="{yy:.1f}" x2="{x + 10:.1f}" '
                           f'y2="{yy:.1f}" stroke="#222" stroke-width="0.8"/>')
                p0 += 2
        acc = ""
        if name != "percussion":
            acc = _acc_from(alter, step, key_map)
            key = (bar_idx, name, step, octave)
            if acc and key not in acc_shown:
                acc_shown[key] = acc
                out.append(f'<text x="{x - 18:.1f}" y="{y + 5:.1f}" '
                           f'font-size="{SPACE * 1.35:.1f}">{acc}</text>')
        out.append(f'<ellipse class="note" data-id="{e.id}" cx="{x:.1f}" cy="{y:.1f}" rx="{SPACE * 0.52:.1f}" '
                   f'ry="{SPACE * 0.40:.1f}" fill="#111" transform="rotate(-12 {x:.1f} {y:.1f})"/>')
        _dur_q = (int(e.release_us or e.onset_us) - int(e.onset_us)) / 500_000
        if any(abs(_dur_q - v) / v < 0.04 for v in (0.75, 1.5, 3.0)):
            out.append(f'<circle cx="{x + SPACE * 0.95:.1f}" cy="{y - SPACE * 0.45:.1f}" '
                       f'r="1.7" fill="#111"/>')
        dur_q = max(0.01, (int(e.release_us or e.onset_us) - int(e.onset_us)) / 500_000)
        up = pos < 4
        sx = x + (SPACE * 0.48 if up else -SPACE * 0.48)
        sy = y - SPACE * 3.4 if up else y + SPACE * 3.4
        out.append(f'<line class="stem" x1="{sx:.1f}" y1="{y:.1f}" x2="{sx:.1f}" '
                   f'y2="{sy:.1f}" stroke="#111" stroke-width="0.9"/>')
        if dur_q < 1.0:
            groups.setdefault((bar_idx, name, up), []).append((x, sx, sy, dur_q))

    # 力度记号（每谱表变化时标）
    _DYN = ((200, "ppp"), (350, "pp"), (500, "p"), (620, "mp"),
            (780, "mf"), (900, "f"), (10_000, "ff"))
    dyn_prev, dyn_x = {}, {}
    for e in _clean(doc):
        name = ("treble" if e.pitch.semitone >= 60 else "bass") \
            if clef == "grand" else clef
        pm = getattr(e.dynamics, "permille", None)
        if pm is None:
            continue
        lab = next((t for hi, t in _DYN if pm < hi), "ff")
        xx = LEFT + (e.onset_us / bar_us) * bar_w
        if dyn_prev.get(name) == lab or xx - dyn_x.get(name, -999) < 60:
            continue
        dyn_prev[name], dyn_x[name] = lab, xx
        yy = ys[staves[-1]] + STAFF_H + 16
        out.append(f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="11" '
                   f'font-style="italic" fill="#333">{lab}</text>')

    # 符杠 + 无杠符尾
    for (bar_idx, name, up), items in groups.items():
        items.sort()
        used = [False] * len(items)
        i = 0
        while i < len(items):
            j = i + 1
            while (j < len(items) and items[j][0] - items[j - 1][0] <= bar_w / 5):
                j += 1
            if j - i >= 2:
                xs = [items[k][1] for k in range(i, j)]
                y_tip = items[i][2]
                out.append(f'<line x1="{min(xs):.1f}" y1="{y_tip:.1f}" '
                           f'x2="{max(xs):.1f}" y2="{y_tip:.1f}" '
                           f'stroke="#111" stroke-width="3.2"/>')
                if all(items[k][3] < 0.5 for k in range(i, j)):
                    yy = y_tip + (7 if up else -7)
                    out.append(f'<line x1="{min(xs):.1f}" y1="{yy:.1f}" '
                               f'x2="{max(xs):.1f}" y2="{yy:.1f}" '
                               f'stroke="#111" stroke-width="2.6"/>')
                for k in range(i, j):
                    used[k] = True
            i = j
        for k, (_x, sx, sy, dur_q) in enumerate(items):
            if used[k]:
                continue
            flags = 3 if dur_q < 0.25 else (2 if dur_q < 0.5 else 1)
            for f in range(flags):
                yy = sy + (f * 7 if up else -f * 7)
                tip = (7 if up else -7)
                out.append(f'<path d="M {sx:.1f},{yy:.1f} C {sx + 9:.1f},{yy + tip:.1f} '
                           f'{sx + 9:.1f},{yy:.1f} {sx:.1f},{yy:.1f}" fill="#111"/>')

    # 整小节休止（该谱表该小节无音）
    rest_y_off = SPACE * 2
    for b in range(nbars):
        for name in staves:
            if b in drawn.get(name, set()):
                continue
            y0 = ys[name]
            out.append(f'<rect x="{LEFT + b * bar_w + bar_w * 0.42:.1f}" '
                       f'y="{y0 + rest_y_off - 2:.1f}" width="12" height="4" '
                       f'fill="#111"/>')

    # 踏板线
    ped = [p_ for p_ in getattr(doc, "pedals", []) if p_.kind in ("sustain", "sostenuto")]
    if ped:
        base = top_y + (len(staves) - 1) * (STAFF_H + SYS_GAP) + STAFF_H + 32
        out.append(f'<line x1="{LEFT - 50:.1f}" y1="{base:.1f}" x2="{width - 12:.1f}" '
                   f'y2="{base:.1f}" stroke="#aaa" stroke-width="0.6"/>')
        out.append(f'<text x="{LEFT - 76:.1f}" y="{base + 4:.1f}" font-size="10" '
                   f'fill="#555">Ped.</text>')
        for p_ in ped[:60]:
            xa = LEFT + (p_.start_us / bar_us) * bar_w
            xb = LEFT + ((p_.end_us or total_us) / bar_us) * bar_w
            out.append(f'<line x1="{xa:.1f}" y1="{base - 4:.1f}" x2="{xb:.1f}" '
                       f'y2="{base - 4:.1f}" stroke="#111" stroke-width="1.2"/>')
    out.append("</g></svg>")
    return "\n".join(out)


def render_text(doc: "ev.MSDocument") -> str:
    """纯文本摘要（CLI/调试用），便于无图形环境下核对。"""
    lines = [f"MSDocument piano_count={doc.piano_count} mode={doc.constraint_mode}",
             f"events={len(doc.events)} pedals={len(doc.pedals)}"]
    for e in sorted(doc.events, key=lambda x: (x.onset_us, x.id)):
        rel = "sustaining" if e.release_us is None else f"{e.release_us}µs"
        lines.append(f"  {e.id}: key={e.key()} onset={e.onset_us}µs release={rel} "
                     f"dyn={e.dynamics.state}/{e.dynamics.permille}")
    for p in doc.pedals:
        lines.append(f"  pedal {p.kind}: {p.start_us}..{p.end_us} depth={p.depth_permille}")
    return "\n".join(lines)

# ── 合并自 ms_render_options.py（2026-10-22 整理） ────────────────

# -*- coding: utf-8 -*-
"""呈现参数（排表 II-1）：`RenderOptions`。

定位：这些参数**只影响"怎么画"**，不属 MS，也不改 MS。
  - MS 只有事件（µs/力度/踏板/键）；**没有**拍号、谱号、调号、小节
  - 要画小节线，必须有 `meter` + `time_base_us`；二者都由**调用方给**
  - 给不出时不得猜：按"无小节语境"处理，并在产物上标注

关键约束（第一原理 P5）：呈现参数不得反写模型；模型也不得为了好画而加字段。
"""

from dataclasses import dataclass, fields

BEAT_TYPES = (1, 2, 4, 8, 16, 32)
CLEFS = ("treble", "bass", "grand")


@dataclass(frozen=True)
class RenderOptions:
    # ── 时间与缩放 ──
    px_per_sec: float = 120.0

    # ── 记谱语境（纯呈现；不属 MS） ──
    meter: tuple | None = None          # (beats, beat_type)，如 (4, 4)
    clef: str = "treble"
    key_sig: int | None = None          # 升降数 −7..7
    time_base_us: int | None = None     # 每四分音符多少微秒（画小节线必需）

    # ── 布局 ──
    bars_per_line: int = 4
    staff_step_px: float = 8.0
    line_width_px: int = 1200

    # ── 标注 ──
    label_missing_context: bool = True  # 缺 meter/time_base 时在图上标注"未指定"

    def __post_init__(self):
        if not (self.px_per_sec > 0):
            raise ValueError("px_per_sec 必须为正")
        if self.staff_step_px <= 0:
            raise ValueError("staff_step_px 必须为正")
        if self.bars_per_line < 1:
            raise ValueError("bars_per_line 必须 ≥1")
        if self.clef not in CLEFS:
            raise ValueError(f"clef 非法：{self.clef!r}（允许 {CLEFS}）")
        if self.key_sig is not None and not (-7 <= self.key_sig <= 7):
            raise ValueError(f"key_sig 必须在 −7..7：{self.key_sig}")
        if self.meter is not None:
            if (not isinstance(self.meter, tuple) or len(self.meter) != 2):
                raise ValueError("meter 必须是 (beats, beat_type)")
            beats, bt = self.meter
            if not (isinstance(beats, int) and beats > 0):
                raise ValueError(f"meter.beats 必须为正整数：{beats!r}")
            if bt not in BEAT_TYPES:
                raise ValueError(f"meter.beat_type 非法：{bt!r}（允许 {BEAT_TYPES}）")
        if self.time_base_us is not None and self.time_base_us <= 0:
            raise ValueError("time_base_us 必须为正")

    # ── 派生 ──
    def bar_duration_us(self) -> int | None:
        """一小节多少微秒；缺 meter 或 time_base 时返回 None（**不猜**）。"""
        if self.meter is None or self.time_base_us is None:
            return None
        beats, bt = self.meter
        return beats * self.time_base_us * 4 // bt

    def beat_duration_us(self) -> int | None:
        if self.meter is None or self.time_base_us is None:
            return None
        return self.time_base_us * 4 // self.meter[1]

    def has_bar_context(self) -> bool:
        return self.bar_duration_us() is not None

    def bar_starts_us(self, total_us: int) -> list:
        """返回所有小节起点；无小节语境时返回空列表（由调用方决定是否画参考线）。"""
        bar = self.bar_duration_us()
        if bar is None:
            return []
        out, t = [], 0
        while t < max(0, total_us):
            out.append(t)
            t += bar
        return out

    def describe(self) -> str:
        """给日志/产物用的可读描述（含"未指定"标注）。"""
        parts = [f"px/s={self.px_per_sec:g}", f"clef={self.clef}"]
        if self.meter:
            parts.append(f"meter={self.meter[0]}/{self.meter[1]}")
        elif self.label_missing_context:
            parts.append("meter=未指定")
        if self.key_sig is not None:
            parts.append(f"key={self.key_sig:+d}")
        if self.time_base_us:
            parts.append(f"time_base={self.time_base_us}µs/♩")
        elif self.label_missing_context:
            parts.append("time_base=未指定（不画小节线）")
        return " ".join(parts)


DEFAULTS = RenderOptions()


def as_dict(opts: "RenderOptions") -> dict:
    d = {f.name: getattr(opts, f.name) for f in fields(opts)}
    d["bar_duration_us"] = opts.bar_duration_us()
    d["has_bar_context"] = opts.has_bar_context()
    return d
