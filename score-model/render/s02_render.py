# -*- coding: utf-8 -*-
"""S02 矢量分析图（P6-2）：一张 SVG 看结构 + 曲线。

三条泳道（横向都是小节，按小节均分）：
  1. 段落带：每个 Section 一个色块 + 标签 + 小节号；
  2. 连续维度曲线：紧张 / 推进 / 留白（0..1 折线）；
  3. 标记：局部扰动（按小节画小竖线）。

只依赖标准库拼接 SVG；不引入绘图库。样式走内联属性，前端可直接当图片看。
"""
from __future__ import annotations

import s02_score
import s02_segment
import s02_weights as wt

W = 980
PAD = 24
ROW_H = 90


def _x(bar: int, total: int) -> float:
    """小节号（1 基）→ 画布 x。"""
    if total <= 0:
        return PAD
    return PAD + (bar - 1) / total * W


def render(score, *, weights=None, title: str = "") -> str:
    """返回 SVG 文本。"""
    cfg = weights or wt.load()
    seg = s02_segment.segment(score, weights=cfg)
    sc = s02_score.analyze_sections(score, seg["sections"], weights=cfg)
    dims = {x["id"]: x for x in sc["sections"]}
    total = max(1, seg.get("bars") or 1)
    events = seg.get("perturb", {}).get("events", [])

    height = PAD * 2 + ROW_H * 3 + 20
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + PAD * 2}" '
           f'height="{height}" viewBox="0 0 {W + PAD * 2} {height}">',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="{PAD}" y="{PAD - 8}" font-size="13" fill="#222">'
           f'{title or score.title or "S02"}</text>']

    # ── 泳道 1：段落带 ──
    y0 = PAD
    colors = {"高潮": "#f4a3a3", "紧张": "#f6c6a0", "密集推进": "#f7e3a1",
              "陈述": "#c9dff2", "安静": "#dff0d8", "留白": "#eeeeee"}
    for x in seg["sections"]:
        x1, x2 = _x(x["start_bar"], total), _x(x["end_bar"] + 1, total)
        fill = colors.get(x["label"], "#ddd")
        out.append(f'<rect class="section sec-{x["id"]}" x="{x1:.1f}" y="{y0}" '
                   f'width="{max(1.0, x2 - x1):.1f}" height="{ROW_H - 18}" fill="{fill}" '
                   f'stroke="#888" stroke-width="0.6"/>')
        d = dims.get(x["id"], {})
        out.append(f'<text x="{x1 + 3:.1f}" y="{y0 + 14}" font-size="10" fill="#333">'
                   f'{x["id"]} {x["label"]}</text>')
        out.append(f'<text x="{x1 + 3:.1f}" y="{y0 + 27}" font-size="8" fill="#666">'
                   f'{x["start_bar"]}–{x["end_bar"]} 小节 · 紧张 {d.get("tension", 0):.2f} · '
                   f'推进 {d.get("drive", 0):.2f}</text>')
    out.append(f'<text x="{PAD}" y="{y0 - 6}" font-size="9" fill="#777">段落</text>')

    # ── 泳道 2：维度曲线 ──
    y1 = PAD + ROW_H
    out.append(f'<line x1="{PAD}" y1="{y1 + 56}" x2="{PAD + W}" y2="{y1 + 56}" '
               f'stroke="#ccc" stroke-width="0.8"/>')
    out.append(f'<text x="{PAD}" y="{y1 - 6}" font-size="9" fill="#777">'
               f'紧张(红) / 推进(蓝) / 留白(绿)</text>')
    for dim, color in (("tension", "#c0392b"), ("drive", "#2c6fb5"), ("space", "#27ae60")):
        pts = []
        for x in seg["sections"]:
            d = dims.get(x["id"], {})
            v = float(d.get(dim) or 0.0)
            xm = (_x(x["start_bar"], total) + _x(x["end_bar"] + 1, total)) / 2
            pts.append(f"{xm:.1f},{y1 + 56 - v * 48:.1f}")
        out.append(f'<polyline class="dim dim-{dim}" points="{" ".join(pts)}" '
                   f'fill="none" stroke="{color}" stroke-width="1.6"/>')
        for pt in pts:
            x, y = pt.split(",")
            out.append(f'<circle cx="{x}" cy="{y}" r="2.2" fill="{color}"/>')

    # ── 泳道 3：扰动标记 ──
    y2 = PAD + ROW_H * 2
    out.append(f'<text x="{PAD}" y="{y2 - 6}" font-size="9" fill="#777">局部扰动</text>')
    seen = set()
    for e in events:
        w = e["window"]
        if w in seen:
            continue
        seen.add(w)
        x = _x(w, total)
        out.append(f'<line class="perturb" x1="{x:.1f}" y1="{y2}" x2="{x:.1f}" '
                   f'y2="{y2 + 60}" stroke="#8e44ad" stroke-width="1"/>')
    # 小节刻度
    step = max(1, total // 20)
    for b in range(1, total + 1, step):
        x = _x(b, total)
        out.append(f'<line x1="{x:.1f}" y1="{y2 + 60}" x2="{x:.1f}" y2="{y2 + 66}" '
                   f'stroke="#aaa" stroke-width="0.6"/>')
        out.append(f'<text x="{x:.1f}" y="{y2 + 76}" font-size="7" fill="#888" '
                   f'text-anchor="middle">{b}</text>')
    out.append("</svg>")
    return "\n".join(out)
