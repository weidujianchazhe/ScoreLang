# -*- coding: utf-8 -*-
"""S02 连续打分与反权重。"""
from __future__ import annotations

import math

import s02_harmony as hm
import s02_perturb as pb
import s02_probe as probe_mod
import s02_weights as wt

DIMS = ("tension", "drive", "space", "bright")


def _sig(z: float) -> float:
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _logit(p: float) -> float:
    p = max(1e-4, min(1 - 1e-4, p))
    return math.log(p / (1 - p))


def _cfg(weights=None) -> dict:
    return (weights or wt.load())["score"]


def _raw(score) -> dict:
    """原始量的逐窗口表：{window: {tension_raw, drive_raw, bright_raw, density}}。"""
    pr = probe_mod.analyze(score)
    hz = hm.analyze(score)
    pt = pb.analyze(score)
    by_perturb = pb.by_window(pt)
    by_h = {w["window"]: w for w in hz["windows"]}

    out = {}
    for b in pr["bars"]:
        w = b["window"]
        h = by_h.get(w, {})
        notes = max(1, int(b.get("notes") or 0))
        chroma = by_perturb.get(w, {}).get("count", 0) / notes
        tension_raw = (0.5 * float(h.get("v_tension_mean") or 0.0)
                       + 0.3 * float(h.get("leap_mean") or 0.0)
                       + 0.2 * min(1.0, chroma))
        out[w] = {
            "tension_raw": round(tension_raw, 4),
            "drive_raw": float(b.get("density") or 0.0),
            "bright_raw": float(b.get("centroid") or 0.0),
            "density": float(b.get("density") or 0.0),
            "notes": notes,
        }
    return out


def score_window(raw: dict, cfg: dict) -> dict:
    """一个窗口的四个维度（0..1）。"""
    return {
        "tension": round(_sig((raw["tension_raw"] - cfg["tension_center"]) / cfg["tension_scale"]), 3),
        "drive": round(_sig((raw["drive_raw"] - cfg["drive_center"]) / cfg["drive_scale"]), 3),
        "space": round(_sig((cfg["space_center"] - raw["density"]) / cfg["space_scale"]), 3),
        "bright": round(_sig((raw["bright_raw"] - cfg["bright_center"]) / cfg["bright_scale"]), 3),
    }


def analyze(score, *, weights=None) -> dict:
    """逐窗口 + 逐段（若给 `sections`）的连续维度。"""
    cfg = _cfg(weights)
    raws = _raw(score)
    windows = []
    for w in sorted(raws):
        row = {"window": w, **score_window(raws[w], cfg), "raw": raws[w]}
        windows.append(row)
    return {"windows": windows, "cfg": cfg}


def aggregate(windows: list, start_bar: int, end_bar: int) -> dict:
    """一段（按小节范围）的维度均值。"""
    part = [x for x in windows if start_bar <= x["window"] <= end_bar]
    if not part:
        return {k: 0.0 for k in DIMS}
    return {k: round(sum(x[k] for x in part) / len(part), 3) for k in DIMS}


def analyze_sections(score, sections: list, *, weights=None) -> dict:
    """把连续维度落到段落上。"""
    res = analyze(score, weights=weights)
    out = []
    for s in sections:
        dims = aggregate(res["windows"], s["start_bar"], s["end_bar"])
        out.append({"id": s["id"], "label": s.get("label"), "start_bar": s["start_bar"],
                    "end_bar": s["end_bar"], **dims})
    return {"sections": out, "windows": res["windows"], "cfg": res["cfg"]}


# ── 反权重：目标语义 → 参数建议 ─────────────────────────

# 维度 → 用哪个原始量承载、反解公式
_INVERSE = {
    "drive": ("density", "drive_center", "drive_scale"),
    "space": ("density", "space_center", "space_scale"),
    "bright": ("centroid", "bright_center", "bright_scale"),
    "tension": ("tension_raw", "tension_center", "tension_scale"),
}


def suggest(target: dict, current: dict, cfg: dict) -> dict:
    """给定目标维度（0..1）与当前原始值，反解出原始参数该调到多少。

    `current` = {"density": x, "centroid": y, "tension_raw": z}（缺的用默认）。
    返回 {"density": {"now","target","delta"}, ...}，并附一句解释。
    """
    out = {}
    cur = {"density": 0.0, "centroid": 64.0, "tension_raw": 0.3, **current}
    for dim, want in target.items():
        if dim not in _INVERSE:
            continue
        key, ck, sk = _INVERSE[dim]
        center, scale = float(cfg[ck]), float(cfg[sk])
        z = _logit(float(want))
        if dim == "space":
            want_raw = center - z * scale        # space 是反向的
        else:
            want_raw = center + z * scale
        now = cur.get(key, center)
        out[key] = {"now": round(now, 2), "target": round(want_raw, 2),
                    "delta": round(want_raw - now, 2),
                    "for": dim, "want": float(want)}
    return out


def explain(sug: dict) -> str:
    if not sug:
        return "没有可反解的维度（支持：" + "、".join(_INVERSE) + "）"
    parts = [f"{v['for']}→{v['want']:.2f}：{k} {v['now']} → {v['target']}"
             f"（{v['delta']:+.2f}）" for k, v in sug.items()]
    return "；".join(parts)
