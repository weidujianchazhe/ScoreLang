# -*- coding: utf-8 -*-
"""数字简谱渲染（排表 II-2 · 阶段2 第一优先）。

只依赖 `MSDocument` + `RenderOptions`（拍号/时基/调号），与 S02 无关。

三种模式（形态未定，全部实现，默认 `melody`）：
  - `melody`：单旋律线（取每个时刻的最高音）
  - `two_hands`：上下两行（以 C4=60 为分界：>=60 上行，<60 下行）
  - `chords`：同刻事件用括号叠写，如 `(1 3 5)`

时值标记依赖"拍长"：只有 `RenderOptions` 同时给了 meter 与 time_base 时才算得出；
给不出时**不猜**——只画音高与顺序，并标注"时值未标注"。

音级映射：以 C 为 1（do），半音用 #/b 前缀；八度以 C4 为基准加点。
"""
from __future__ import annotations

import ms_events as ev

LEFT_PAD = 24.0
LINE_H = 96.0
TOP_PAD = 40.0

# 半音类 → (级数, 变音)：0→1, 1→#1, 2→2, 3→b3, 4→3, 5→4, 6→#4, 7→5, 8→b6, 9→6, 10→b7, 11→7
_DEGREE = {0: (1, 0), 1: (1, 1), 2: (2, 0), 3: (3, -1), 4: (3, 0), 5: (4, 0),
           6: (4, 1), 7: (5, 0), 8: (6, -1), 9: (6, 0), 10: (7, -1), 11: (7, 0)}

MODES = ("melody", "two_hands", "chords")


def _degree_of(semitone: int) -> tuple:
    pc = semitone % 12
    octave = semitone // 12 - 1
    deg, alter = _DEGREE[pc]
    return deg, alter, octave


def _duration_marks(duration_us: int, beat_us: int | None) -> tuple:
    """返回 (时值文本标记, 下划线数)。beat 未知时返回 ("", 0)。"""
    if not beat_us:
        return "", 0
    ratio = duration_us / beat_us
    if abs(ratio - 2.0) < 0.05:
        return "—", 0
    if abs(ratio - 1.5) < 0.05:
        return "·", 0
    if abs(ratio - 1.0) < 0.05:
        return "", 0
    for n, target in ((1, 0.5), (2, 0.25), (3, 0.125)):
        if abs(ratio - target) < 0.02:
            return "", n
    return "", 0


def _group_events(doc, mode: str) -> list:
    """按模式把事件分成"行 → 音组"。每组是同一行的同时刻事件集合（组内按音高升序）。"""
    evs = sorted(doc.events, key=lambda e: (e.onset_us, e.pitch.semitone))
    if mode == "melody":
        rows = {"": evs}
    elif mode == "two_hands":
        rows = {"上": [e for e in evs if e.pitch.semitone >= 60],
                "下": [e for e in evs if e.pitch.semitone < 60]}
    elif mode == "chords":
        rows = {"": evs}
    else:
        raise ValueError(f"未知简谱模式：{mode!r}（允许 {MODES}）")

    out = []
    for label, group in rows.items():
        by_time = {}
        for e in group:
            by_time.setdefault(e.onset_us, []).append(e)
        out.append((label, [by_time[t] for t in sorted(by_time)]))
    return out


def render_jianpu(doc: "ev.MSDocument", options=None, mode: str = "melody",
                  warnings: list | None = None) -> str:
    if warnings is not None:
        warnings.extend(ev.check_realization(doc))
    if mode not in MODES:
        raise ValueError(f"未知简谱模式：{mode!r}（允许 {MODES}）")

    px_per_sec = options.px_per_sec if options is not None else 120.0
    beat_us = options.beat_duration_us() if options is not None else None

    end = 0
    for e in doc.events:
        end = max(end, e.release_us if e.release_us is not None else e.onset_us)
    width = max(60.0, (end / 1_000_000) * px_per_sec)
    rows = _group_events(doc, mode)
    height = TOP_PAD + LINE_H * max(1, len(rows)) + 30

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + LEFT_PAD:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width + LEFT_PAD:.0f} {height:.0f}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>']

    if options is not None and options.label_missing_context and beat_us is None:
        out.append(f'<text class="no-beat" x="{LEFT_PAD:.0f}" y="14" font-size="10" fill="#999">'
                   f'时值未标注（缺拍号或时基） | {options.describe()}</text>')

    for row_i, (label, groups) in enumerate(rows):
        base_y = TOP_PAD + row_i * LINE_H + (0 if row_i == 0 else 20)
        if label:
            out.append(f'<text x="2" y="{base_y - 12:.1f}" font-size="10" fill="#666">{label}</text>')
        for group in groups:
            x = LEFT_PAD + (group[0].onset_us / 1_000_000) * px_per_sec
            # 组内按音高升序；chords 全取，melody/two_hands 取该行最高音
            picked = group if mode == "chords" else [group[-1]]
            texts = []
            for e in picked:
                deg, alter, octv = _degree_of(e.pitch.semitone)
                acc = "#" if alter > 0 else ("b" if alter < 0 else "")
                texts.append(f"{acc}{deg}")
            if len(texts) > 1:
                body = "(" + " ".join(texts) + ")"
            else:
                body = texts[0]
            mark, underlines = _duration_marks(
                (group[0].release_us - group[0].onset_us) if group[0].release_us else 0, beat_us)
            out.append(f'<text class="jp-note" data-ids="{",".join(e.id for e in group)}" '
                       f'x="{x:.1f}" y="{base_y:.1f}" font-size="16" fill="#111">{body}{mark}</text>')
            # 高低八度点（以 C4 为基准），以实际画出的那个音为准
            ref = picked[-1]
            octv = ref.pitch.semitone // 12 - 1
            for k in range(abs(octv - 4)):
                cy = base_y - 14 - k * 5 if octv > 4 else base_y + 14 + k * 5
                out.append(f'<circle class="jp-dot" cx="{x + 6:.1f}" cy="{cy:.1f}" r="1.6" fill="#111"/>')
            # 时值下划线
            for k in range(underlines):
                uy = base_y + 4 + k * 3
                out.append(f'<line class="jp-underline" x1="{x:.1f}" y1="{uy:.1f}" '
                           f'x2="{x + 14:.1f}" y2="{uy:.1f}" stroke="#111" stroke-width="0.9"/>')

    out.append("</svg>")
    return "\n".join(out)
