# -*- coding: utf-8 -*-
"""S02 分段与语义标签：把逐窗口特征变成段落、句读与标签。"""
from __future__ import annotations

import s02_harmony as hm
import s02_probe as probe_mod
import s02_weights as wt


def _series(bars: list) -> dict:
    return {
        "density": [float(b.get("density") or 0.0) for b in bars],
        "tension": [float(b.get("v_tension_mean") or 0.0) for b in bars],
        "centroid": [float(b.get("centroid") or 0.0) for b in bars],
        "vel_std": [float(b.get("vel_std") or 0.0) for b in bars],
    }


def _z(values: list) -> list:
    if not values:
        return []
    m = sum(values) / len(values)
    sd = (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5 or 1.0
    return [(v - m) / sd for v in values]


def _sse(cols: list, a: int, b: int) -> float:
    tot = 0.0
    for c in cols:
        seg = c[a:b]
        if not seg:
            continue
        m = sum(seg) / len(seg)
        tot += sum((x - m) ** 2 for x in seg)
    return tot


def boundaries(bars: list, cfg: dict) -> list:
    """分段：**段内方差下降**贪心切分（不是逐小节看突变）。

    逐小节看突变会被"一两小节的密度尖峰"骗到（真实谱会切出几十段）。
    正确做法是：切一刀必须让"段内方差"显著下降，否则不切。
    阈值：`split_ratio`（相对总方差）+ `min_section_bars`（最小段长）。
    """
    s = _series(bars)
    cols = [_z(s[k]) for k in ("density", "centroid", "vel_std")]
    n = len(bars)
    if n < 2 * int(cfg["min_section_bars"]):
        return []
    min_bars = int(cfg["min_section_bars"])
    ratio = float(cfg["split_ratio"])
    total0 = _sse(cols, 0, n) or 1.0
    segs = [(0, n)]
    while True:
        best = None
        for (a, b) in segs:
            base = _sse(cols, a, b)
            for cut in range(a + min_bars, b - min_bars + 1):
                imp = base - _sse(cols, a, cut) - _sse(cols, cut, b)
                if best is None or imp > best[0]:
                    best = (imp, a, b, cut)
        if not best or best[0] / total0 < ratio:
            break
        imp, a, b, cut = best
        segs.remove((a, b))
        segs += [(a, cut), (cut, b)]
        segs.sort()
    return [b for (_a, b) in segs[:-1]]


def _label(mean: dict, cfg: dict) -> tuple:
    """按规则给段落贴标签，并返回依据。"""
    d, t, c = mean["density"], mean["tension"], mean["centroid"]
    hi_d = d >= cfg["density_high"]
    lo_d = d <= cfg["density_low"]
    hi_t = t >= cfg["tension_high"]
    lo_t = t <= cfg["tension_low"]
    hi_c = c >= cfg["centroid_high"]
    lo_c = c <= cfg["centroid_low"]

    if hi_d and hi_t:
        lab, why = "高潮", f"密度 {d:.1f} ≥ {cfg['density_high']}，张力 {t:.2f} ≥ {cfg['tension_high']}"
    elif lo_d and lo_t:
        lab, why = "留白", f"密度 {d:.1f} ≤ {cfg['density_low']}，张力 {t:.2f} ≤ {cfg['tension_low']}"
    elif hi_t:
        lab, why = "紧张", f"张力 {t:.2f} ≥ {cfg['tension_high']}"
    elif hi_d:
        lab, why = "密集推进", f"密度 {d:.1f} ≥ {cfg['density_high']}"
    elif lo_d:
        lab, why = "安静", f"密度 {d:.1f} ≤ {cfg['density_low']}"
    else:
        lab, why = "陈述", f"密度 {d:.1f}、张力 {t:.2f} 居中"
    if hi_c:
        why += "；音区偏高"
    elif lo_c:
        why += "；音区偏低"
    return lab, why


def _mean(bars: list, key: str):
    vals = [b.get(key) for b in bars if b.get(key) is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def segment(score, *, weights=None) -> dict:
    """返回 {sections, phrases, bars}。每段带特征均值与标签。"""
    cfg = weights or wt.load()
    pr = probe_mod.analyze(score)
    hz = hm.analyze(score)
    bars = pr["bars"]
    by_win = {b["window"]: b for b in bars}
    for h in hz.get("windows", []):
        if h["window"] in by_win:
            by_win[h["window"]].update({k: v for k, v in h.items() if k != "window"})

    cuts = boundaries(bars, cfg["segment"])
    starts = [0] + cuts
    ends = cuts + [len(bars)]

    # L3 局部扰动：微观细节修正宏观语义（扰动多的段，紧张度上调、标签可能变）
    try:
        import s02_perturb
        pt = s02_perturb.analyze(score, weights=cfg)
        events = pt["events"]
        per_window = s02_perturb.by_window(pt)
        tension_step = float(cfg["perturb"]["tension_per_event"])
    except Exception:
        events, per_window, tension_step = [], {}, 0.0
        pt = {"events": [], "windows": [], "overall": {}}

    sections = []
    ids = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for n, (a, b) in enumerate(zip(starts, ends)):
        chunk = bars[a:b]
        if not chunk:
            continue
        mean = {k: _mean(chunk, k) for k in
                ("density", "v_tension_mean", "centroid", "vel_std", "leap_mean")}
        base_tension = mean["v_tension_mean"] or 0.0
        n_ev = sum(1 for e in events if a + 1 <= e["window"] <= b)
        n_notes = sum(int(x.get("notes") or 0) for x in chunk) or 1
        # 扰动比例：每 5% 的音是扰动就算"满"，最多抬 tension_step
        ratio = min(1.0, (n_ev / n_notes) / 0.05) if n_ev else 0.0
        adj_tension = min(1.0, base_tension + tension_step * ratio)
        lab, why = _label({"density": mean["density"] or 0.0,
                           "tension": adj_tension,
                           "centroid": mean["centroid"] or 0.0}, cfg["label"])
        if n_ev:
            why += (f"；含 {n_ev} 处扰动（{n_ev / n_notes:.1%}，"
                    f"紧张度 {base_tension:.2f}→{adj_tension:.2f}）")
        sec = {
            "id": f"S{ids[n % 26]}",
            "start_bar": a + 1,
            "end_bar": b,
            "bars": b - a,
            "notes": sum(int(x.get("notes") or 0) for x in chunk),
            "label": lab,
            "why": why,
            "features": mean,
            "repeat": _repeat_of(chunk),
            "perturb": n_ev,
            "tension_adj": round(adj_tension, 3),
        }
        sections.append(sec)

    phrases = _phrases(score, sections, bars, cfg)
    return {"sections": sections, "phrases": phrases, "bars": len(bars),
            "perturb": {"events": events, "overall": (pt["overall"] if per_window else {})}}


def _repeat_of(chunk: list) -> str:
    exact = sum(1 for b in chunk if str(b.get("repeat") or "-").startswith("exact"))
    trans = sum(1 for b in chunk if str(b.get("repeat") or "-").startswith("transposed"))
    if not chunk:
        return "-"
    if exact + trans == 0:
        return "无重复"
    return f"重复 {exact} 窗" + (f"、移调 {trans} 窗" if trans else "")


def _phrases(score, sections: list, bars: list, cfg: dict) -> list:
    """句读：段内遇到"长音开始"或"整窗无音"就切一短语。"""
    bar = max(1, score.grid_units_per_quarter * max(1, score.time_beats))
    long_units = int(cfg["segment"]["phrase_long_note_bars"]) * bar
    long_starts = {int(n.onset // bar) + 1 for n in score.notes if n.duration >= long_units}
    silent = {int(b["window"]) for b in bars if int(b.get("notes") or 0) == 0}

    out = []
    min_bars = int(cfg["segment"].get("min_phrase_bars", 2))
    for sec in sections:
        marks = sorted({m for m in (long_starts | silent)
                        if sec["start_bar"] < m <= sec["end_bar"]})
        kept, last = [], sec["start_bar"]
        for m in marks:                       # 少于 min_bars 的句读丢弃（避免碎成一片）
            if m - last >= min_bars:
                kept.append(m)
                last = m
        edges = [sec["start_bar"]] + kept + [sec["end_bar"] + 1]
        for i, (a, b) in enumerate(zip(edges, edges[1:])):
            if b - a <= 0:
                continue
            out.append({"id": f"{sec['id']}{i + 1}", "section": sec["id"],
                        "start_bar": a, "end_bar": b - 1,
                        "reason": "长音起句" if a in long_starts else
                                  ("休止" if a in silent else "段首")})
    return out


def to_text(result: dict) -> str:
    out = ["段  小节      音数  密度  张力  音区  标签      依据"]
    out.append("--  --------  ----  ----  ----  ----  --------  ----")
    for s in result["sections"]:
        f = s["features"]
        out.append("{}   {:2d}–{:2d}     {:3d}  {:4.1f}  {:4.2f}  {:4.0f}  {:8s}  {}".format(
            s["id"], s["start_bar"], s["end_bar"], s["notes"],
            f["density"] or 0, f["v_tension_mean"] or 0, f["centroid"] or 0,
            s["label"], s["why"]))
    out.append("")
    out.append("短语：" + "、".join(f"{p['id']}({p['start_bar']}–{p['end_bar']})"
                                    for p in result["phrases"]))
    return "\n".join(out)
