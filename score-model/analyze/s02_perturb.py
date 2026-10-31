# -*- coding: utf-8 -*-
"""S02 局部扰动：找出打破常规的那几个音或小节。"""
from __future__ import annotations

import s02_weights as wt

PC_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _rolling_median(by_win: dict, window: int, line: str, span: int = 2, _cache=None):
    """该声部在 window±span 内的音高中位数（用来判断"突然翻上去/砸下去"）。"""
    key = (line, window)
    if _cache is not None and key in _cache:
        return _cache[key]
    vals = []
    for w in range(window - span, window + span + 1):
        for n in by_win.get(w, []):
            if getattr(n, "voice", None) == line:
                vals.append(n.pitch.semitone)
    if len(vals) < 3:
        med = None
    else:
        vals.sort()
        med = vals[len(vals) // 2]
    if _cache is not None:
        _cache[key] = med
    return med


MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11)


def _scale_pcs(score, min_coverage: float = 0.75) -> set:
    """用**调式模板**推断调：12 个大调模板里选覆盖率最高的那个。

    比"取出现最多的 7 个音级"稳：后者在音乐稀疏或临时记号多时会把调外音当调内音
    （或反过来把大量调内音当调外音——本曲实测就出过 316 条假阳性）。
    覆盖率 < 75% 时判为"无明确调"→ 返回空集，此时不报调外音（宁缺勿滥）。
    """
    hist = {}
    for n in score.notes:
        pc = n.pitch.semitone % 12
        hist[pc] = hist.get(pc, 0) + 1
    total = sum(hist.values()) or 1
    best, best_cov = None, 0.0
    for root in range(12):
        pcs = {(root + s) % 12 for s in MAJOR_STEPS}
        cov = sum(hist.get(pc, 0) for pc in pcs) / total
        if cov > best_cov:
            best, best_cov = pcs, cov
    return best if best_cov >= min_coverage else set()


def analyze(score, *, weights=None) -> dict:
    """返回 `{events, windows, overall}`；events 是逐条扰动，可核对。"""
    cfg = (weights or wt.load())["perturb"]
    accent_z = float(cfg["accent_z"])
    accent_abs = float(cfg["accent_abs"])
    register_jump = float(cfg["register_jump"])
    density_slope = float(cfg["density_slope"])

    bar = max(1, score.grid_units_per_quarter * max(1, score.time_beats))
    scale = _scale_pcs(score)

    by_win = {}
    for n in score.notes:
        by_win.setdefault(n.onset // bar, []).append(n)

    events = []
    windows = []
    prev_density = None
    med_cache = {}            # (声部, 窗口) → 附近中位音高（P7 性能：避免每音重算重排）
    for w in sorted(by_win):
        notes = by_win[w]
        vels = [n.dynamics_permille for n in notes if n.dynamics_permille is not None]
        mean_v = sum(vels) / len(vels) if vels else 0.0
        sd_v = (sum((v - mean_v) ** 2 for v in vels) / len(vels)) ** 0.5 if len(vels) > 1 else 0.0
        centroid = sum(n.pitch.semitone for n in notes) / len(notes)
        density = len(notes)

        for n in notes:
            # 1) 力度偏移
            v = n.dynamics_permille
            if v is not None and sd_v > 0:
                z = (v - mean_v) / sd_v
                if z >= accent_z and (v - mean_v) >= accent_abs:
                    events.append({"kind": "accent", "window": w + 1, "note": n.id,
                                   "value": v, "strength": round(min(1.0, z / 3.0), 3),
                                   "detail": f"力度 {v} 比本节均值 {mean_v:.0f} 高 {v - mean_v:.0f}"})
            # 2) 半音外音
            pc = n.pitch.semitone % 12
            if scale and pc not in scale:
                events.append({"kind": "chromatic", "window": w + 1, "note": n.id,
                               "value": pc, "strength": 0.8,
                               "detail": f"音级 {PC_NAMES[pc]} 不在推断调式内（{sorted(PC_NAMES[p] for p in scale)}）"})
            # 3) 音区突变：与该声部前后几小节的中位音高比（不是与本窗口重心比，
            #    否则"一个宽音域小节"里每个音都会被标成突变）
            med = _rolling_median(by_win, w, getattr(n, "voice", None), _cache=med_cache)
            if med is not None and abs(n.pitch.semitone - med) >= register_jump:
                events.append({"kind": "register", "window": w + 1, "note": n.id,
                               "value": n.pitch.semitone,
                               "strength": round(min(1.0, abs(n.pitch.semitone - med) / (register_jump * 2)), 3),
                               "detail": f"音高 {n.pitch.semitone} 比该声部附近中位 {med} 高/低 "
                                         f"{abs(n.pitch.semitone - med):.0f} 半音"})

        # 4) 密度斜率
        if prev_density is not None and prev_density > 0:
            rel = (density - prev_density) / prev_density
            if abs(rel) >= density_slope:
                events.append({"kind": "density", "window": w + 1, "note": None,
                               "value": round(rel, 3), "strength": round(min(1.0, abs(rel)), 3),
                               "detail": f"密度 {prev_density}→{density}（{rel:+.0%}）"})
        prev_density = density

        local = [e for e in events if e["window"] == w + 1]
        score_p = min(1.0, sum(e["strength"] for e in local) / 4.0)
        windows.append({"window": w + 1, "count": len(local), "perturb": round(score_p, 3)})

    overall = {
        "events": len(events),
        "by_kind": {k: sum(1 for e in events if e["kind"] == k)
                    for k in ("accent", "chromatic", "register", "density")},
        "scale": sorted(PC_NAMES[p] for p in scale),
        "max_window": max((x["perturb"] for x in windows), default=0.0),
    }
    return {"events": events, "windows": windows, "overall": overall}


def by_window(result: dict) -> dict:
    return {x["window"]: x for x in result["windows"]}


def label(event: dict) -> str:
    return {"accent": "突强", "chromatic": "调外音",
            "register": "音区突变", "density": "密度突变"}[event["kind"]]
