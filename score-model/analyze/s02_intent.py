# -*- coding: utf-8 -*-
"""意图核对：把“想表达什么”与报告里的测量值对齐（只报符合/偏离，不判好坏）。"""
from __future__ import annotations


def _get(m: dict, k: str):
    v = (m or {}).get(k)
    return v


def compare(intent: dict, quality: dict) -> dict:
    """intent → 每层 {target, measured, status}；status ∈ 符合/偏离/无法判断。

    intent 支持（都可省略）：
      structure:  {"balanced": True}
      expression: {"expectation": 0.0..1.0, "release_late": True}
      ending:     {"stagger_voices": True, "fade": True}
      technique:  {"density": "low" | "medium" | "high"}
    """
    m = (quality or {}).get("metrics") or {}
    meas = (quality or {}).get("measurements") or {}
    exp = meas.get("expectation_release") or {}
    tech = meas.get("technique_density") or {}
    out = {"layers": {}, "note": "只判断“是否符合意图”，不判断曲子好坏"}

    def layer(name, target, measured, ok, why=""):
        out["layers"][name] = {
            "target": target, "measured": measured,
            "status": "无法判断" if measured is None else ("符合" if ok else "偏离"),
            "why": why,
        }

    s = (intent or {}).get("structure") or {}
    if "balanced" in s:
        v = _get(m, "structure")
        layer("structure", s, v, v is not None and v >= 0.55,
              "段落均衡指标 ≥0.55 视为均衡")

    e = (intent or {}).get("expression") or {}
    if "expectation" in e:
        v = exp.get("peak_at")
        tgt = float(e["expectation"])
        # 期待越高 → 峰值越靠后（0.5 以下算早）
        layer("expression", e, v, v is not None and v >= tgt * 0.9,
              "峰值位置靠后 = 期待更久")
    if e.get("release_late") is True:
        v = exp.get("fall")
        layer("expression_release", {"release_late": True}, v,
              v is not None and v >= 0.3, "峰值后回落充分 = 释放")

    end = (intent or {}).get("ending") or {}
    if end.get("stagger_voices") is True:
        v = _get(m, "ending_voices")
        layer("ending", end, v, v is not None and v >= 0.5,
              "各声部收束指标 ≥0.5")

    t = (intent or {}).get("technique") or {}
    if "density" in t:
        want = str(t["density"])
        v = tech.get("per_note")
        if v is None:
            layer("technique", t, None, False)
        else:
            lo, hi = (0.0, 0.08) if want == "low" else (
                (0.08, 0.25) if want == "medium" else (0.25, 1.0))
            layer("technique", t, v, lo <= v < hi,
                  "技术密度测量值（高低与好坏无关，只看是否符合意图）")
    return out


__all__ = ["compare"]
