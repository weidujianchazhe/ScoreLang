# -*- coding: utf-8 -*-
"""S02 客观特征探针：把 ScoreV02 算成逐小节的特征表。"""
from __future__ import annotations

BLOCKS = "▁▂▃▄▅▆▇█"


def _spark(values, lo=None, hi=None) -> str:
    """把一串数值画成块状曲线（无数据返回空串）。"""
    if not values:
        return ""
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    if hi <= lo:
        return BLOCKS[0] * len(values)
    out = []
    for v in values:
        k = int(round((v - lo) / (hi - lo) * (len(BLOCKS) - 1)))
        out.append(BLOCKS[max(0, min(len(BLOCKS) - 1, k))])
    return "".join(out)


def _intervals(notes) -> list:
    """小节内按时间的相邻音音程（半音差）。"""
    seq = [n.pitch.semitone for n in sorted(notes, key=lambda n: (n.onset, n.id))]
    return [b - a for a, b in zip(seq, seq[1:])]


def _rhythm_signature(notes) -> tuple:
    """节奏型：相对时值（以最短音为单位），移调不变。"""
    durs = [n.duration for n in sorted(notes, key=lambda n: (n.onset, n.id)) if n.duration > 0]
    if not durs:
        return ()
    g = 0
    for d in durs:
        g = d if g == 0 else _gcd(g, d)
    return tuple(d // g for d in durs)


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


def _max_polyphony(notes) -> int:
    """小节内最大同时发声数（同 onset 的算同时）。"""
    events = []
    for n in notes:
        events.append((n.onset, 1))
        events.append((n.onset + max(1, n.duration), -1))
    events.sort()
    cur = peak = 0
    for _t, d in events:
        cur += d
        peak = max(peak, cur)
    return peak


def analyze(score, *, bars_per_window: int = 1) -> dict:
    """逐小节（或每 N 小节一个窗口）算特征。返回 dict，可直接 json.dumps。"""
    gq = max(1, score.grid_units_per_quarter)
    bar_len = max(1, gq * max(1, score.time_beats))
    win = max(1, int(bars_per_window)) * bar_len

    buckets = {}
    for n in score.notes:
        buckets.setdefault(n.onset // win, []).append(n)

    bars = []
    seen = {}                      # signature → first window index
    for w in sorted(buckets):
        notes = buckets[w]
        semis = [n.pitch.semitone for n in notes]
        vels = [n.dynamics_permille for n in notes if n.dynamics_permille is not None]
        ivs = _intervals(notes)
        rhythm = _rhythm_signature(notes)
        sig = (tuple(ivs), rhythm)
        repeat = "-"
        if sig in seen and len(ivs) > 0:
            prev = seen[sig]
            a, b = buckets[prev], notes
            if a[0].pitch.semitone == b[0].pitch.semitone:
                repeat = f"exact:{prev + 1}"
            else:
                repeat = f"transposed:{b[0].pitch.semitone - a[0].pitch.semitone:+d}@{prev + 1}"
        else:
            seen[sig] = w
        bars.append({
            "window": w + 1,
            "start": w * win,
            "end": w * win + win,
            "notes": len(notes),
            "density": round(len(notes) / (win / gq / max(1, score.time_beats)), 3),
            "vel_mean": round(sum(vels) / len(vels), 1) if vels else None,
            "vel_std": round(_std(vels), 1) if len(vels) > 1 else 0.0,
            "centroid": round(sum(semis) / len(semis), 2) if semis else None,
            "span": (max(semis) - min(semis)) if semis else 0,
            "poly": _max_polyphony(notes),
            "intervals": ivs,
            "repeat": repeat,
        })

    # 补齐空窗口（含休止）：否则「以休止起句」永远不会触发，且全曲窗口数失真
    if bars:
        have = {b["window"]: b for b in bars}
        filled = []
        for w in range(1, max(have) + 1):
            if w in have:
                filled.append(have[w])
                continue
            start = (w - 1) * win
            filled.append({
                "window": w, "start": start, "end": start + win,
                "notes": 0, "density": 0.0, "vel_mean": None, "vel_std": 0.0,
                "centroid": None, "span": 0, "poly": 0,
                "intervals": [], "repeat": "-",
            })
        bars = filled

    all_vels = [n.dynamics_permille for n in score.notes if n.dynamics_permille is not None]
    all_semis = [n.pitch.semitone for n in score.notes]
    summary = {
        "notes": len(score.notes),
        "windows": len(bars),
        "grid": gq,
        "bar_units": bar_len,
        "actions": len(score.actions),
        "curves": len(score.curves),
        "pedals": len(score.pedal_marks),
        "segments": len(score.segments),
        "pitch_range": (min(all_semis), max(all_semis)) if all_semis else None,
        "vel_range": (min(all_vels), max(all_vels)) if all_vels else None,
        "repeat_ratio": round(sum(1 for b in bars if b["repeat"] != "-") / len(bars), 3)
        if bars else 0.0,
    }
    return {"summary": summary, "bars": bars,
            "spark": {"density": _spark([b["notes"] for b in bars]),
                      "centroid": _spark([b["centroid"] or 0 for b in bars]),
                      "vel_std": _spark([b["vel_std"] for b in bars])}}


def _std(values) -> float:
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5


def format_table(result: dict, limit: int = 40) -> str:
    """把探针结果排成对照表（人看的版本）。"""
    bars = result["bars"][:limit]
    out = ["win  notes  dens  vel_μ   vel_σ  cents  span  poly  repeat",
           "---  -----  ----  ------  -----  -----  ----  ----  ------"]
    for b in bars:
        out.append("{:3d}  {:5d}  {:4.2f}  {:6}  {:5.1f}  {:5}  {:4d}  {:4d}  {}".format(
            b["window"], b["notes"], b["density"],
            f"{b['vel_mean']:.0f}" if b["vel_mean"] is not None else "-",
            b["vel_std"], f"{b['centroid']:.0f}" if b["centroid"] is not None else "-",
            b["span"], b["poly"], b["repeat"]))
    if len(result["bars"]) > limit:
        out.append(f"… 还有 {len(result['bars']) - limit} 个窗口")
    s = result["spark"]
    out += ["", "密度   " + s["density"], "音区   " + s["centroid"], "力度σ  " + s["vel_std"]]
    return "\n".join(out)
