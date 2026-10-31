# -*- coding: utf-8 -*-
"""S02 张力 / 协和 / 声部干涉（固定常数，零权重）。"""
from __future__ import annotations

# 音程级（半音数 mod 12）→ 协和度 0..1（固定表，来源：常用乐理分类）
CONSONANCE = {
    0: 1.00,   # 纯一度
    1: 0.08,   # 小二度
    2: 0.25,   # 大二度
    3: 0.65,   # 小三度
    4: 0.80,   # 大三度
    5: 0.95,   # 纯四度
    6: 0.10,   # 三全音
    7: 1.00,   # 纯五度
    8: 0.70,   # 小六度
    9: 0.80,   # 大六度
    10: 0.30,  # 小七度
    11: 0.12,  # 大七度
}


def consonance(semitone_interval: int) -> float:
    """任意音程的协和度（八度等价）。"""
    return CONSONANCE[abs(int(semitone_interval)) % 12]


def vertical_tension(notes) -> float:
    """同刻一组音 → 张力 0..1（两两不协和取平均）。单音/空 → 0。"""
    if len(notes) < 2:
        return 0.0
    pairs = 0
    total = 0.0
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            total += 1.0 - consonance(notes[i].pitch.semitone - notes[j].pitch.semitone)
            pairs += 1
    return round(total / pairs, 4) if pairs else 0.0


def leap_tension(semitone_interval: int) -> float:
    """旋律跳进张力：级进≈0，越大越紧张；超过八度显著更紧张。"""
    d = abs(int(semitone_interval))
    if d <= 2:
        return 0.05 * d
    if d <= 7:
        return 0.10 + 0.05 * (d - 2)
    if d <= 12:
        return 0.35 + 0.05 * (d - 7)
    return min(1.0, 0.70 + 0.02 * (d - 12))


def _voices(score) -> dict:
    """按 (乐器, 声部) 分线，供干涉计算。"""
    out = {}
    for n in sorted(score.notes, key=lambda x: (x.onset, x.id)):
        out.setdefault((n.instrument_id, n.voice), []).append(n)
    return out


def interference(score) -> dict:
    """声部干涉：反向/同向进行、声部交叉。

    比较"同一乐器内不同声部"在同一时间窗（±1 个网格）里的相邻音走向。
    """
    lines = _voices(score)
    by_inst = {}
    for (inst, voice), notes in lines.items():
        by_inst.setdefault(inst, {})[voice] = notes

    contrary = similar = crossing = 0
    tol = max(1, score.grid_units_per_quarter // 4)
    for inst, voices in by_inst.items():
        names = sorted(voices)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a_notes, b_notes = voices[names[i]], voices[names[j]]
                # 原实现是"每个 a 对逐个 b 试"，7448 音的曲子跑出 370 万次比较（3.1s）。
                # 两条线都按 onset 排序，用滑动窗口只比 |Δonset| ≤ tol 的对。
                j0 = 0
                for a0, a1 in zip(a_notes, a_notes[1:]):
                    while j0 < len(b_notes) - 1 and b_notes[j0].onset < a0.onset - tol:
                        j0 += 1
                    k = j0
                    while k < len(b_notes) - 1 and b_notes[k].onset <= a0.onset + tol:
                        b0, b1 = b_notes[k], b_notes[k + 1]
                        da = a1.pitch.semitone - a0.pitch.semitone
                        db = b1.pitch.semitone - b0.pitch.semitone
                        if da * db < 0:
                            contrary += 1
                        elif da * db > 0:
                            similar += 1
                        if (a0.pitch.semitone - b0.pitch.semitone) * (
                                a1.pitch.semitone - b1.pitch.semitone) < 0:
                            crossing += 1
                        k += 1
    return {"contrary": contrary, "similar": similar, "crossing": crossing}


def analyze(score, *, window_units: int | None = None) -> dict:
    """逐窗口的张力/协和/干涉。窗口默认 1 小节。"""
    bar = max(1, score.grid_units_per_quarter * max(1, score.time_beats))
    win = int(window_units or bar)

    by_win = {}
    for n in score.notes:
        by_win.setdefault(n.onset // win, []).append(n)

    # 旋律线只分一次（P7 性能）：原来在每个窗口里重算 _voices 并线性过滤，
    # 大曲子是 O(窗口数 × 音符数)，7448 音的曲子这里占 1.7s。
    voices = _voices(score)
    line_by_win = {}          # 窗口 → [该窗口里的各条线音符]
    for line in voices.values():
        buckets = {}
        for n in line:
            buckets.setdefault(n.onset // win, []).append(n)
        for w, seq in buckets.items():
            line_by_win.setdefault(w, []).append(seq)

    windows = []
    for w in sorted(by_win):
        notes = by_win[w]
        # 同刻分组算纵向张力
        by_on = {}
        for n in notes:
            by_on.setdefault(n.onset, []).append(n)
        v = [vertical_tension(g) for g in by_on.values() if len(g) > 1]
        # 横向：同一声部内相邻音
        leaps = []
        chromatic = 0
        for seq in line_by_win.get(w, []):
            for a, b in zip(seq, seq[1:]):
                d = b.pitch.semitone - a.pitch.semitone
                leaps.append(leap_tension(d))
                if abs(d) == 1:
                    chromatic += 1
        windows.append({
            "window": w + 1,
            "v_tension_mean": round(sum(v) / len(v), 4) if v else 0.0,
            "v_tension_max": round(max(v), 4) if v else 0.0,
            "leap_mean": round(sum(leaps) / len(leaps), 4) if leaps else 0.0,
            "leap_max": round(max(leaps), 4) if leaps else 0.0,
            "chromatic": chromatic,
        })

    inter = interference(score)
    overall = {
        "v_tension": round(sum(x["v_tension_mean"] for x in windows) / len(windows), 4)
        if windows else 0.0,
        "leap_mean": round(sum(x["leap_mean"] for x in windows) / len(windows), 4)
        if windows else 0.0,
        **inter,
    }
    return {"windows": windows, "overall": overall}
