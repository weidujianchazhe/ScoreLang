# -*- coding: utf-8 -*-
"""S02 指法与物理可行性：最小手模型。"""
from __future__ import annotations

import s02_weights as wt


def _hand(semitone: int) -> str:
    """兜底分线：中央 C（60）以下算左手（没有声部信息时用）。"""
    return "LH" if semitone < 60 else "RH"


def _line(n) -> str:
    """按**声部**分线：同一声部才可能要求同一只手同时按住几个音。

    只按音高分左右手会把"旋律音 + 伴奏音"当成一个大和弦（跨度 20+ 半音），
    那是错判——它们是不同声部，本来就不要求同一只手。
    """
    return getattr(n, "voice", None) or _hand(n.pitch.semitone)


def _split_clusters(semis: list, gap_split: int = 7, min_notes: int = 3,
                    two_hand_gap: int = 17, hard_limit: int = 16) -> list:
    """把同刻的一组音拆成"各自一只手"的簇。

    规则（经验但可解释）：
      · 2 个音：间隔 ≥ 17 半音（比十度还大）才拆成两只手；
        十度以内（12–16）当成**同一只手的伸张**，不算两只手；
      · ≥3 个音：相邻间隙 ≥ 7 半音（纯五度）就断开——再大更像另一只手/另一声部；
      · 任何簇跨过十度（>16）就继续按最大间隙拆，直到落进一只手的范围。
    """
    def split(semis):
        if len(semis) == 2:
            return [semis] if (semis[1] - semis[0]) < two_hand_gap \
                else [[semis[0]], [semis[1]]]
        if len(semis) < min_notes:
            return [semis]
        out, cur = [], [semis[0]]
        for s in semis[1:]:
            if s - cur[-1] >= gap_split:
                out.append(cur)
                cur = [s]
            else:
                cur.append(s)
        out.append(cur)
        return out

    def refine(cluster):
        if len(cluster) < 2 or cluster[-1] - cluster[0] <= hard_limit:
            return [cluster]
        gaps = [(cluster[i + 1] - cluster[i], i) for i in range(len(cluster) - 1)]
        g, i = max(gaps)
        if g < 3:
            return [cluster]          # 没有明显缝隙，就是一只手的伸张
        return refine(cluster[:i + 1]) + refine(cluster[i + 1:])

    semis = sorted(semis)
    out = []
    for cluster in split(semis):
        out.extend(refine(cluster))
    return out


def _groups(notes, *, gap_split: int = 12) -> list:
    """同刻 + 同声部 → [(onset, line, [簇音高...])]，按时间排序。"""
    by = {}
    for n in notes:
        by.setdefault((n.onset, _line(n)), []).append(n.pitch.semitone)
    out = []
    for (onset, line), semis in sorted(by.items()):
        for cluster in _split_clusters(semis, gap_split=gap_split):
            out.append((onset, line, cluster))
    return out


def _center(group) -> float:
    return sum(n.pitch.semitone for n in group) / len(group)


def analyze(score, *, weights=None) -> dict:
    """逐小节的手部可行性（**按左右手分别算**）。返回 `{windows, overall, hard_bars}`。"""
    cfg = (weights or wt.load())["fingering"]
    span_ok = float(cfg["span_limit"])
    span_bad = float(cfg["hard_limit"])
    jump_ok = float(cfg["jump_limit"])

    bar = max(1, score.grid_units_per_quarter * max(1, score.time_beats))
    windows = []
    prev_center = {}          # 声部 → 上次手位中心（声部名不固定：RH / RH2 / LH3 …）
    by_bar = {}               # 预分桶（P7 性能：原来每个窗口都线性扫全曲音符）
    for n in score.notes:
        by_bar.setdefault(n.onset // bar, []).append(n)
    if not by_bar:
        return {"windows": [], "overall": {"max_span": 0, "max_jump": 0.0,
                                           "stretch_bars": 0, "span_limit": span_ok,
                                           "hard_limit": span_bad}, "hard_bars": []}
    for w in range(0, max(by_bar) + 1):
        bar_notes = by_bar.get(w, [])
        if not bar_notes:
            continue
        span_max = 0
        jump_max = 0.0
        stretch = 0
        for onset, line, semis in _groups(bar_notes):
            span = max(semis) - min(semis) if semis else 0
            span_max = max(span_max, span)
            if span > span_ok:
                stretch += 1
            c = sum(semis) / len(semis) if semis else 0.0
            prev = prev_center.get(line)
            if prev is not None:
                jump_max = max(jump_max, abs(c - prev))
            prev_center[line] = c
        hard = 0.0
        if span_max > span_ok:
            hard = max(hard, min(1.0, (span_max - span_ok) / max(1.0, span_bad - span_ok)))
        if jump_max > jump_ok:
            hard = max(hard, min(1.0, (jump_max - jump_ok) / max(1.0, jump_ok)))
        windows.append({
            "window": w + 1,
            "notes": len(bar_notes),
            "hand_span": span_max,
            "hand_jump": round(jump_max, 1),
            "stretch": stretch,
            "hard": round(hard, 3),
        })

    hard_bars = [x for x in windows if x["hard"] > 0]
    overall = {
        "max_span": max((x["hand_span"] for x in windows), default=0),
        "max_jump": max((x["hand_jump"] for x in windows), default=0.0),
        "stretch_bars": len(hard_bars),
        "span_limit": span_ok,
        "hard_limit": span_bad,
    }
    return {"windows": windows, "overall": overall, "hard_bars": hard_bars}


def label(window: dict) -> str:
    """一句人话结论（给报告用）。"""
    if window["hard"] <= 0:
        return "正常"
    if window["hand_span"] >= 16:
        return "跨度超十度（多数手够不到）"
    if window["hand_span"] > 12:
        return "跨度超八度（需要大手）"
    return "手位移动大（速度快时难）"
