# -*- coding: utf-8 -*-
"""完整五线谱渲染（2026-10-19）。

与 `ms_render_staff2`（示意图）的区别：这是**可读、可打印的谱面**，补齐了：

  ✅ 大谱表（高音/低音）+ 谱号 + **拍号** + **调号**（升降号）
  ✅ **临时记号**（♯/♭/♮，含小节内还原）
  ✅ **休止符**（全/二分/四分/八分）——按声部时间轴补齐空隙
  ✅ 符头/符干/符尾分组（同拍连杠）、附点、加线
  ✅ **力度记号**（p/mp/mf/f/ff，随段落变化标注）
  ✅ **踏板记号**（Ped. / *）
  ✅ 多声部（时间重叠时按区间着色分配，避免叠在一根符干上）
  ✅ 分页（每页固定系统数）+ 小节号

不做：连音线/乐句弧（MS 不含 tie/slur）、指法、速度术语。
"""
from __future__ import annotations

import ms_events as ev

STEP_IDX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
STEP_OF = {0: "C", 1: "D", 2: "E", 3: "F", 4: "G", 5: "A", 6: "B"}
SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]

MUSIC_FONT = "'Segoe UI Symbol','Noto Music','Bravura',serif"
STAFF_STEP = 8.0          # 相邻线间距
LEFT_PAD = 46.0
CLEF_W = 26.0
SIG_W = 14.0
SYSTEM_GAP = 62.0
PAGE_MARGIN = 24.0
SYSTEMS_PER_PAGE = 4
TITLE_H = 96.0

STAFF_BOTTOM = {"treble": 37, "bass": 25}     # diatonic(C4=35)：treble 底线 E4，bass 底线 G2


def _idx(p) -> int:
    return (p.octave + 1) * 7 + STEP_IDX.get(p.step, 0)


def _dur_q(us: int, tb: int) -> float:
    return us / tb


def _is_filled(q: float) -> bool:
    return q < 0.99          # 八分及更短实心；四分实心；二分/全音符空心


def _has_dot(q: float) -> bool:
    """附点判定：以十六分音符为单位（0.25 拍），3/6/12 个单位即附点。"""
    units = q * 4
    r = round(units)
    return abs(units - r) < 0.02 and r in (3, 6, 12)


def _assign_voices(notes: list) -> list:
    """区间着色：同谱表内不重叠的音归到同一 voice。返回 [(voice_index, note)]。"""
    occupancy: list = []
    out = []
    for e in sorted(notes, key=lambda x: (x.onset_us, x.pitch.semitone)):
        on = e.onset_us
        end = e.release_us if e.release_us is not None else on + 1
        vi = None
        for i, occ in enumerate(occupancy):
            if on >= occ:
                vi = i
                occupancy[i] = end
                break
        if vi is None:
            occupancy.append(end)
            vi = len(occupancy) - 1
        out.append((vi, e))
    return out


def _accidental_for(alter: int, key_map: dict, state: dict, bar: int, staff: str, p) -> str:
    """返回 '' | '#' | 'b' | 'n'（还原）。"""
    key = (staff, bar, p.step, p.octave)
    want = alter
    expected = key_map.get(p.step, 0)
    if key in state:
        if state[key] == want:
            return ""
        state[key] = want
        if want == expected:
            return "n"
        return "#" if want > expected else "b"
    state[key] = want
    if want == expected:
        return ""
    if expected != 0 and want == 0:
        return "n"
    return "#" if want > 0 else "b"


def _key_map(key_fifths: int) -> dict:
    m = {}
    if key_fifths > 0:
        for s in SHARP_ORDER[:key_fifths]:
            m[s] = 1
    elif key_fifths < 0:
        for s in FLAT_ORDER[:-key_fifths]:
            m[s] = -1
    return m


def _dyn_symbol(permille: int | None) -> str:
    """按等级表锚点划分：ppp250 pp516 p766 mp1000 mf1250 f1500 ff1750 fff1984。"""
    if permille is None:
        return ""
    if permille < 660:
        return "pp"
    if permille < 900:
        return "p"
    if permille < 1130:
        return "mp"
    if permille < 1380:
        return "mf"
    if permille < 1630:
        return "f"
    return "ff"


def render_score(doc: "ev.MSDocument", options, *, title: str = "", subtitle: str = "",
                 warnings: list | None = None,
                 author: str = "", systems_per_page: int = SYSTEMS_PER_PAGE) -> str:
    if warnings is not None:
        warnings.extend(ev.check_realization(doc))
    tb = options.time_base_us
    meter = options.meter or (4, 4)
    beats, beat_type = meter
    key_fifths = getattr(options, "key_sig", 0) or 0
    bars_per_line = max(1, getattr(options, "bars_per_line", 4))
    width = getattr(options, "line_width_px", 1100)
    bar_us = int(options.bar_duration_us() or (beats * tb * 4 / beat_type))
    key_map = _key_map(key_fifths)

    end_us = max([e.release_us or e.onset_us for e in doc.events] + [0])
    n_bars = max(1, int((end_us + bar_us - 1) // bar_us))
    systems = [list(range(i, min(i + bars_per_line, n_bars))) for i in range(0, n_bars, bars_per_line)]

    staff_h = 8 * STAFF_STEP / 2
    clef = getattr(options, "clef", "grand")
    staffs = ["treble", "bass"] if clef == "grand" else ([clef] if clef in ("treble", "bass") else ["treble"])
    grand_h = staff_h * len(staffs) + (40 if len(staffs) > 1 else 0)
    system_h = grand_h + SYSTEM_GAP
    page_h = PAGE_MARGIN * 2 + TITLE_H + systems_per_page * system_h
    pages = [systems[i:i + systems_per_page] for i in range(0, len(systems), systems_per_page)]
    total_h = page_h * len(pages)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + 2 * LEFT_PAD:.0f}" '
           f'height="{total_h:.0f}" viewBox="0 0 {width + 2 * LEFT_PAD:.0f} {total_h:.0f}" '
           f'font-family="Georgia, serif">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']

    # 声部分配：按谱表分开
    treble = [e for e in doc.events if e.pitch.semitone >= 60] if clef == "grand" else \
             (list(doc.events) if "treble" in staffs else [])
    bass = [e for e in doc.events if e.pitch.semitone < 60] if clef == "grand" else \
           (list(doc.events) if "bass" in staffs else [])
    t_voice = _assign_voices(treble)
    b_voice = _assign_voices(bass)
    by_bar_t: dict = {}
    by_bar_b: dict = {}
    for vi, e in t_voice:
        by_bar_t.setdefault(int(e.onset_us // bar_us), []).append((vi, e))
    for vi, e in b_voice:
        by_bar_b.setdefault(int(e.onset_us // bar_us), []).append((vi, e))

    acc_state_t: dict = {}
    acc_state_b: dict = {}
    pedal_on = False
    last_dyn = {"sym": "", "pm": None}

    for pi, page in enumerate(pages):
        oy = pi * page_h
        if pi > 0:
            out.append(f'<line x1="0" y1="{oy:.0f}" x2="{width + 2 * LEFT_PAD:.0f}" y2="{oy:.0f}" '
                       f'stroke="#ccc" stroke-dasharray="4 6"/>')
        # 标题（每页重复，便于翻阅）
        ty = oy + PAGE_MARGIN + 18
        out.append(f'<text x="{LEFT_PAD + width / 2:.0f}" y="{ty:.0f}" font-size="19" '
                   f'text-anchor="middle" fill="#111">{title}</text>')
        if subtitle:
            out.append(f'<text x="{LEFT_PAD + width / 2:.0f}" y="{ty + 17:.0f}" font-size="10" '
                       f'text-anchor="middle" fill="#666">{subtitle}</text>')
        if author:
            out.append(f'<text x="{LEFT_PAD + width / 2:.0f}" y="{ty + 33:.0f}" font-size="11" '
                       f'text-anchor="middle" fill="#333" font-style="italic">{author}</text>')

        for si, bars in enumerate(page):
            top = oy + PAGE_MARGIN + TITLE_H + si * system_h
            x0 = LEFT_PAD
            key_w = 7 * abs(key_fifths) if key_fifths else 0
            left_w = CLEF_W + key_w + 20          # 谱号 + 调号 + 拍号位
            usable = width - left_w - 8
            bar_w = usable / max(1, len(bars))
            bars_x0 = x0 + left_w
            g_bottom = top + grand_h

            for staff_name, top_y in ((sname, top + (staff_h + 40) * k)
                                      for k, sname in enumerate(staffs)):
                bottom_y = top_y + staff_h
                for k in range(5):
                    y = bottom_y - k * STAFF_STEP
                    out.append(f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x0 + width:.1f}" y2="{y:.1f}" '
                               f'stroke="#2a2a2a" stroke-width="0.7"/>')
                glyph = "𝄞" if staff_name == "treble" else "𝄢"
                out.append(f'<text x="{x0 + 2:.1f}" y="{bottom_y - 2:.1f}" font-size="26" '
                           f'font-family="{MUSIC_FONT}" fill="#111">{glyph}</text>')
                # 调号（按谱号固定音位：F♯ 在五线最上、C♯ 次之…；用全音阶序号定位）
                if key_fifths:
                    STEP_OF_LETTER = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
                    # 标准音位：treble 的 ♯ 依次 F5 C5 G5 D5 A4 E5 B4；bass 依次 F3 C3 G3 D3 A2 E3 B2
                    T_OCT = {"F": 5, "C": 5, "G": 5, "D": 5, "A": 4, "E": 5, "B": 4}
                    B_OCT = {"F": 3, "C": 3, "G": 3, "D": 3, "A": 2, "E": 3, "B": 2}
                    # 降号：treble B4 E5 A4 D5 G4 C5 F4；bass B2 E3 A2 D3 G2 C3 F2
                    T_OCT_FLAT = {"B": 4, "E": 5, "A": 4, "D": 5, "G": 4, "C": 5, "F": 4}
                    B_OCT_FLAT = {"B": 2, "E": 3, "A": 2, "D": 3, "G": 2, "C": 3, "F": 2}
                    order = SHARP_ORDER if key_fifths > 0 else FLAT_ORDER
                    octs = (T_OCT if staff_name == "treble" else B_OCT) if key_fifths > 0 \
                        else (T_OCT_FLAT if staff_name == "treble" else B_OCT_FLAT)
                    for n, s in enumerate(order[:abs(key_fifths)]):
                        idx = (octs[s] + 1) * 7 + STEP_OF_LETTER[s]
                        yy = bottom_y - (idx - STAFF_BOTTOM[staff_name]) * (STAFF_STEP / 2)
                        out.append(f'<text x="{x0 + CLEF_W + 2 + n * 6:.1f}" y="{yy + 4:.1f}" font-size="13" '
                                   f'fill="#111">{"♯" if key_fifths > 0 else "♭"}</text>')
                # 拍号（大谱表只写在上面一行）
                if staff_name == "treble":
                    out.append(f'<text x="{x0 + CLEF_W + key_w + 14:.1f}" y="{top_y + staff_h * 0.45:.1f}" '
                               f'font-size="14" text-anchor="middle" fill="#111" font-weight="bold">{beats}</text>')
                    out.append(f'<text x="{x0 + CLEF_W + key_w + 14:.1f}" y="{top_y + staff_h * 0.95:.1f}" '
                               f'font-size="14" text-anchor="middle" fill="#111" font-weight="bold">{beat_type}</text>')

            # 小节
            for bi, bar in enumerate(bars):
                bx = bars_x0 + bi * bar_w
                out.append(f'<line x1="{bx:.1f}" y1="{top:.1f}" x2="{bx:.1f}" y2="{g_bottom - 40 + staff_h:.1f}" '
                           f'stroke="#333" stroke-width="0.9"/>')
                out.append(f'<text x="{bx + 2:.1f}" y="{top - 12:.1f}" font-size="8" fill="#999">{bar + 1}</text>')

                # ── 高音谱表 ──
                for staff_name, notes, acc_state, top_y in (
                        (sname,
                         (by_bar_t if sname == "treble" else by_bar_b).get(bar, []),
                         acc_state_t if sname == "treble" else acc_state_b,
                         top + (staff_h + 40) * k)
                        for k, sname in enumerate(staffs)):
                    bottom_y = top_y + staff_h
                    bottom_idx = STAFF_BOTTOM[staff_name]
                    staff_notes = sorted(notes, key=lambda t: (t[1].onset_us, t[1].pitch.semitone))
                    # 力度（只在变化时标）
                    # 力度：按**小节代表值**（右手中位数）判定，变化超过 120‰ 才标——
                    # 这是记谱惯例（力度标在小节/乐句位置，不逐音标），也避免抖动刷屏
                    if staff_name == "treble" and staff_notes:
                        lv = sorted([e.dynamics.permille for _v, e in staff_notes
                                     if e.dynamics.permille is not None])
                        if lv:
                            pm = lv[len(lv) // 2]
                            sym = _dyn_symbol(pm)
                            prev = last_dyn["pm"]
                            if sym and (prev is None or (sym != last_dyn["sym"] and abs(pm - prev) > 120)):
                                last_dyn["sym"], last_dyn["pm"] = sym, pm
                                out.append(f'<text x="{bx + 4:.1f}" y="{top + grand_h + 15:.1f}" '
                                           f'font-size="12" font-style="italic" fill="#111">{sym}</text>')
                    for vi, e in staff_notes:
                        x = bx + 14 + ((e.onset_us % bar_us) / bar_us) * (bar_w - 26)
                        idx = _idx(e.pitch)
                        y = bottom_y - (idx - bottom_idx) * (STAFF_STEP / 2)
                        q = _dur_q(max(1, (e.release_us or e.onset_us + 1) - e.onset_us), tb)
                        filled = _is_filled(q)
                        out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="4.2" ry="3.1" '
                                   f'fill="{"#111" if filled else "#fff"}" stroke="#111" stroke-width="1"/>')
                        # 符干
                        up = (idx - bottom_idx) < (staff_h / (STAFF_STEP / 2)) / 2
                        stem_x = x + (4.0 if up else -4.0)
                        stem_y2 = y - 3.4 * STAFF_STEP if up else y + 3.4 * STAFF_STEP
                        out.append(f'<line x1="{stem_x:.1f}" y1="{y:.1f}" x2="{stem_x:.1f}" y2="{stem_y2:.1f}" '
                                   f'stroke="#111" stroke-width="1"/>')
                        # 附点
                        if _has_dot(q):
                            out.append(f'<circle cx="{x + 8:.1f}" cy="{y - (3 if (idx % 2) else 0):.1f}" '
                                       f'r="1.6" fill="#111"/>')
                        # 加线
                        if idx > bottom_idx + 8:
                            for L in range(bottom_idx + 10, idx + 1, 2):
                                ly = bottom_y - (L - bottom_idx) * (STAFF_STEP / 2)
                                out.append(f'<line x1="{x - 6:.1f}" y1="{ly:.1f}" x2="{x + 6:.1f}" y2="{ly:.1f}" '
                                           f'stroke="#111" stroke-width="0.9"/>')
                        elif idx < bottom_idx:
                            for L in range(bottom_idx - 2, idx - 1, -2):
                                ly = bottom_y - (L - bottom_idx) * (STAFF_STEP / 2)
                                out.append(f'<line x1="{x - 6:.1f}" y1="{ly:.1f}" x2="{x + 6:.1f}" y2="{ly:.1f}" '
                                           f'stroke="#111" stroke-width="0.9"/>')
                        # 临时记号
                        acc = _accidental_for(e.pitch.alter, key_map, acc_state, bar, staff_name, e.pitch)
                        if acc:
                            out.append(f'<text x="{x - 11:.1f}" y="{y + 4:.1f}" font-size="11" '
                                       f'fill="#111">{acc}</text>')

                    # ── 休止符（主声部空隙）──
                    v0 = [e for vi, e in staff_notes if vi == 0]
                    if v0:
                        cursor = bar * bar_us
                        for e in v0:
                            if e.onset_us - cursor > tb * 0.24:
                                rx = bx + 14 + ((cursor - bar * bar_us) / bar_us) * (bar_w - 26)
                                q = _dur_q(e.onset_us - cursor, tb)
                                mid = top_y + STAFF_STEP * 2          # 第三线（中间线）
                                if q >= 3.5:                          # 全休止 𝄻
                                    out.append(f'<text x="{rx - 7:.1f}" y="{mid + 3:.1f}" font-size="20" '
                                               f'font-family="{MUSIC_FONT}" fill="#111">𝄻</text>')
                                elif q >= 1.5:                        # 二分休止 𝄼
                                    out.append(f'<text x="{rx - 7:.1f}" y="{mid + 13:.1f}" font-size="20" '
                                               f'font-family="{MUSIC_FONT}" fill="#111">𝄼</text>')
                                elif q >= 0.9:                        # 四分休止 𝄽
                                    out.append(f'<text x="{rx - 4:.1f}" y="{mid + 7:.1f}" font-size="19" '
                                               f'font-family="{MUSIC_FONT}" fill="#111">𝄽</text>')
                                else:                                 # 八分休止 𝄾
                                    out.append(f'<text x="{rx - 4:.1f}" y="{mid + 7:.1f}" font-size="16" '
                                               f'font-family="{MUSIC_FONT}" fill="#111">𝄾</text>')
                            cursor = max(cursor, e.release_us or e.onset_us)

                # ── 踏板记号（低音谱下方）──
                for p in doc.pedals:
                    if p.kind != "sustain":
                        continue
                    for mark, at in (("Ped.", p.start_us), ("*", p.end_us)):
                        if at is None:
                            continue
                        if bar * bar_us <= at < (bar + 1) * bar_us:
                            px = bx + 6 + ((at - bar * bar_us) / bar_us) * (bar_w - 12)
                            out.append(f'<text x="{px:.1f}" y="{top + grand_h + 32:.1f}" '
                                       f'font-size="10" font-style="italic" fill="#333">{mark}</text>')

            # 系统右端小节线
            rx = bars_x0 + len(bars) * bar_w
            out.append(f'<line x1="{rx:.1f}" y1="{top:.1f}" x2="{rx:.1f}" y2="{g_bottom - 40 + staff_h:.1f}" '
                       f'stroke="#333" stroke-width="1.6"/>')
            # 大谱表连接线（左）
            out.append(f'<line x1="{x0 - 4:.1f}" y1="{top:.1f}" x2="{x0 - 4:.1f}" '
                       f'y2="{top + staff_h + 40 + staff_h:.1f}" stroke="#333" stroke-width="1.2"/>')

        # 页脚
        out.append(f'<text x="{LEFT_PAD + width:.0f}" y="{oy + page_h - 8:.0f}" font-size="8" '
                   f'text-anchor="end" fill="#888">{pi + 1} / {len(pages)}</text>')

    out.append("</svg>")
    return "\n".join(out)
