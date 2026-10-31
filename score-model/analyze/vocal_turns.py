# -*- coding: utf-8 -*-
"""人声转折（收束层）：一个字占 2–3 个音时，第 2、3 个音「该怎么转」。

MS 以**音**为单位；汉字只是把这 2–3 个音编成一组（`bind`），让它们之间有转折。

判定顺序（先用显式数据，再按时间推导——缺的从来不是规则，是"该怎么转"）：

  1. `COMBO_RULES` 命中 `combo` → 用它声明的 kind / strength（组合类型是权威声明）
  2. `xfade_us > 0`            → **liaison** 连音：与前音按 xfade 叠
  3. 间隙 == 0                 → **restrike** 重起：韵母重起音，不叠
  4. 间隙 ≥ `min_breath_ms`     → **breath** 换气：气口（间隙已在时间轴里）
  5. 其余                      → **break** 断：不叠，也不额外加工

`overlap_us`：>0 与前音重叠，0 不叠；渲染层直接用这个量。
时间可行性沿用 `ms_instruments` 的转折因子（人声 `min_breath_ms=100`），
所以推导出的转折**不会**被 V16 判不可行；组合类型硬指定的若与间隙矛盾，
收束层记 `V-turn-infeasible` 而不静默改判。
"""
from __future__ import annotations

DEFAULT_MIN_BREATH_MS = 100          # ms_instruments: vocal_fold.min_breath_ms

#: 组合类型（combo）→ (kind, strength)。**编码表待定稿**：留空时全部按时间推导。
#: 例：{"S0001": ("liaison", 0), "S0002": ("restrike", 700), "S0003": ("breath", 600)}
COMBO_RULES: dict = {}

#: 各转折的缺省音头强度（0 = 几乎无痕；1000 = 正常重音）
DEFAULT_STRENGTH = {"liaison": 0, "restrike": 700, "breath": 600, "break": 300}

KINDS = ("liaison", "restrike", "breath", "break")


def min_breath_us(constraints: dict | None = None) -> int:
    """人声换气的最短气口（微秒）。取乐器约束，缺省按机制默认。"""
    cons = constraints or {}
    return int(cons.get("min_breath_ms", DEFAULT_MIN_BREATH_MS) * 1000)


def decide(*, xfade_us: int = 0, gap_us: int = 0, prev_dur_us: int = 0,
           combo: str | None = None, constraints: dict | None = None) -> dict:
    """返回一个音的转折决定：{kind, strength, overlap_us, reason, feasible}。"""
    breath_us = min_breath_us(constraints)

    rule = COMBO_RULES.get(combo or "")
    if rule is not None:
        kind, strength = rule
        overlap = int(xfade_us) if kind == "liaison" else 0
        if kind == "liaison" and overlap <= 0 and prev_dur_us:
            overlap = int(prev_dur_us * 0.15)
        feasible = True
        if kind == "liaison" and int(xfade_us) < 0:
            feasible = False
        if kind == "breath" and gap_us < breath_us:
            feasible = False
        return {"kind": kind, "strength": int(strength), "overlap_us": overlap,
                "reason": "combo", "feasible": feasible}

    if int(xfade_us) > 0:
        overlap = int(xfade_us)
        return {"kind": "liaison", "strength": DEFAULT_STRENGTH["liaison"],
                "overlap_us": overlap, "reason": "xfade", "feasible": True}
    if gap_us == 0:
        return {"kind": "restrike", "strength": DEFAULT_STRENGTH["restrike"],
                "overlap_us": 0, "reason": "abut", "feasible": True}
    if gap_us >= breath_us:
        return {"kind": "breath", "strength": DEFAULT_STRENGTH["breath"],
                "overlap_us": 0, "reason": "gap", "feasible": True}
    return {"kind": "break", "strength": DEFAULT_STRENGTH["break"],
            "overlap_us": 0, "reason": "short-gap", "feasible": True}
