# -*- coding: utf-8 -*-
"""S02 大数据校准（P5）：用参照曲目把"拍脑袋阈值"换成"分位数"。

做法（可复核）：
  1. 把参照曲目跑一遍，收集**原始量**（不含任何打分）：`tension_raw` / `density` / `centroid`；
  2. 取分位数：
       center = p50（中位数）          scale = (p75 − p25) / 2
     这样"中等曲子"落在 0.5 附近，"前半数/后半数"大致分开；
  3. 标签阈值同样取分位：`density_high = p75`、`density_low = p25`、`tension_high = p75` …
  4. 产出 `weights.calibrated.toml`（**不覆盖**默认值）+ 一份对比报告。

纪律：本模块只**统计**，不判断好坏；"多少算密集"从此有数据出处（哪几首、哪个分位）。
"""
from __future__ import annotations

from pathlib import Path

import s02_score as score_mod
import s02_weights as wt


def percentile(values: list, p: float) -> float:
    """线性插值分位数（p 取 0..1）。"""
    if not values:
        return 0.0
    vs = sorted(values)
    if len(vs) == 1:
        return float(vs[0])
    k = (len(vs) - 1) * max(0.0, min(1.0, p))
    lo, hi = int(k), min(len(vs) - 1, int(k) + 1)
    frac = k - lo
    return float(vs[lo] * (1 - frac) + vs[hi] * frac)


def collect(scores: list, *, weights=None) -> dict:
    """收集参照曲目的原始量。

    · 窗口级：给 `[score]` 的 center/scale 用（维度是逐窗口算的）；
    · **段级**：给 `[label]` 的阈值用——标签是打在段落上的，
      用窗口分位数去卡段均值会系统性偏严（实测把整首都判成"陈述"）。
    """
    import s02_segment

    tens, dens, cent, per_piece = [], [], [], []
    sec_d, sec_t, sec_c = [], [], []
    cfg = weights or wt.load()
    for s in scores:
        raws = score_mod._raw(s)
        t = [r["tension_raw"] for r in raws.values()]
        d = [r["density"] for r in raws.values()]
        c = [r["bright_raw"] for r in raws.values()]
        tens += t
        dens += d
        cent += c
        try:
            seg = s02_segment.segment(s, weights=cfg)
            for x in seg.get("sections", []):
                f = x.get("features") or {}
                sec_d.append(float(f.get("density") or 0.0))
                sec_t.append(float(x.get("tension_adj") or f.get("v_tension_mean") or 0.0))
                sec_c.append(float(f.get("centroid") or 0.0))
        except Exception:
            pass
        per_piece.append({"notes": len(s.notes), "windows": len(t),
                          "density_mean": round(sum(d) / len(d), 2) if d else 0.0})
    return {"tension_raw": tens, "density": dens, "centroid": cent,
            "sec_density": sec_d, "sec_tension": sec_t, "sec_centroid": sec_c,
            "pieces": per_piece}


def derive(collected: dict) -> dict:
    """分位数 → 校准后的 center/scale（窗口级）与标签阈值（段级）。"""
    t, d, c = collected["tension_raw"], collected["density"], collected["centroid"]
    sd = collected.get("sec_density") or d
    st = collected.get("sec_tension") or t
    sc = collected.get("sec_centroid") or c

    def band(vals):
        lo, mid, hi = percentile(vals, 0.25), percentile(vals, 0.50), percentile(vals, 0.75)
        return mid, max(1e-3, (hi - lo) / 2.0), lo, hi

    t_mid, t_scale, _t_lo, _t_hi = band(t)
    d_mid, d_scale, _d_lo, _d_hi = band(d)
    c_mid, c_scale, _c_lo, _c_hi = band(c)

    return {
        "score": {
            "tension_center": round(t_mid, 4), "tension_scale": round(t_scale, 4),
            "drive_center": round(d_mid, 3), "drive_scale": round(d_scale, 3),
            "space_center": round(d_mid, 3), "space_scale": round(d_scale, 3),
            "bright_center": round(c_mid, 2), "bright_scale": round(c_scale, 2),
        },
        # 标签阈值用**段级**分位数（标签打在段上）
        "label": {
            "density_high": round(percentile(sd, 0.75), 2),
            "density_low": round(percentile(sd, 0.25), 2),
            "tension_high": round(percentile(st, 0.75), 3),
            "tension_low": round(percentile(st, 0.25), 3),
            "centroid_high": round(percentile(sc, 0.75), 1),
            "centroid_low": round(percentile(sc, 0.25), 1),
        },
        "stats": {
            "samples": len(d),
            "sections": len(sd),
            "pieces": len(collected["pieces"]),
            "tension_p10": round(percentile(t, 0.10), 3),
            "tension_p90": round(percentile(t, 0.90), 3),
            "density_p10": round(percentile(d, 0.10), 2),
            "density_p90": round(percentile(d, 0.90), 2),
            "centroid_p10": round(percentile(c, 0.10), 1),
            "centroid_p90": round(percentile(c, 0.90), 1),
        },
    }


def write_toml(derived: dict, path, *, meta: dict | None = None) -> Path:
    """写 `weights.calibrated.toml`（只含被校准的段，其余用默认）。"""
    p = Path(path)
    lines = ["# S02 校准权重（由 tools 生成，不覆盖 s02_weights.DEFAULTS）"]
    for k, v in (meta or {}).items():
        lines.append(f"# {k}: {v}")
    for section in ("score", "label"):
        lines.append("")
        lines.append(f"[{section}]")
        for k, v in derived[section].items():
            lines.append(f"{k} = {v}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def report(derived: dict, *, current: dict | None = None, path=None) -> str:
    """校准前后对比（markdown）。"""
    cur = (current or wt.load())
    st = derived["stats"]
    out = ["# S02 权重校准报告", "",
           f"- 样本：{st['samples']} 个窗口 / {st['pieces']} 首曲子", "",
           "## 1. 分布（分位数）", "",
           "| 量 | p10 | p50 | p90 |", "|---|---|---|---|"]
    out.append(f"| 张力 raw | {st['tension_p10']} | "
               f"{derived['score']['tension_center']} | {st['tension_p90']} |")
    out.append(f"| 密度 | {st['density_p10']} | {derived['score']['drive_center']} | "
               f"{st['density_p90']} |")
    out.append(f"| 音区 | {st['centroid_p10']} | {derived['score']['bright_center']} | "
               f"{st['centroid_p90']} |")
    out += ["", "## 2. 阈值：默认 → 校准", "",
            "| 键 | 默认 | 校准 | 变化 |", "|---|---|---|---|"]
    for section in ("score", "label"):
        for k, v in derived[section].items():
            old = (cur.get(section) or {}).get(k)
            if old is None:
                continue
            delta = "" if not isinstance(old, (int, float)) else f"{v - old:+.3f}"
            out.append(f"| {section}.{k} | {old} | {v} | {delta} |")
    out += ["", "> 校准只改 `[score]` 与 `[label]`；其余段（segment/perturb/fingering）保持默认。"]
    text = "\n".join(out) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text
