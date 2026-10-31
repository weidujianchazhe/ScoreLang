# -*- coding: utf-8 -*-
"""写谱层 · 奏法参数表。"""
from __future__ import annotations

VERSION = "articulation-v1"

# 千分比：gate=时长系数，vel=力度修正
from semantics import ARTICULATIONS


def gate_pm(articulation: str) -> int:
    if articulation not in ARTICULATIONS:
        raise KeyError(f"未知奏法：{articulation!r}（允许 {sorted(ARTICULATIONS)}）")
    return ARTICULATIONS[articulation]["gate_pm"]


def vel_pm(articulation: str) -> int:
    if articulation not in ARTICULATIONS:
        raise KeyError(f"未知奏法：{articulation!r}（允许 {sorted(ARTICULATIONS)}）")
    return ARTICULATIONS[articulation]["vel_pm"]


def apply_duration(duration_us: int, articulation: str) -> int:
    """按奏法缩短时长（四舍五入到整数微秒）。"""
    g = gate_pm(articulation)
    return (int(duration_us) * g + 500) // 1000


def apply_dynamics(permille: int | None, articulation: str) -> int | None:
    """按奏法修正力度。`None`（未提供）保持 `None` —— 缺失不得被奏法"补成"数值。"""
    if permille is None:
        return None
    v = vel_pm(articulation)
    return (int(permille) * v + 500) // 1000


def apply(duration_us: int, permille: int | None, articulation: str) -> tuple:
    return apply_duration(duration_us, articulation), apply_dynamics(permille, articulation)


def table() -> dict:
    return {k: dict(v) for k, v in ARTICULATIONS.items()}
