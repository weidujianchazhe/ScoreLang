# -*- coding: utf-8 -*-
"""写谱层 · 默认力度等级表。"""
from __future__ import annotations

LEVELS_VERSION = "dyn-levels-v1"

# 等级 → MIDI velocity（来自常见记谱软件的默认力度档）
VELOCITY = {
    "ppp": 16,
    "pp": 33,
    "p": 49,
    "mp": 64,
    "mf": 80,
    "f": 96,
    "ff": 112,
    "fff": 127,
}

ANCHOR_VELOCITY = 64
ANCHOR_PERMILLE = 1000


def velocity_to_permille(velocity: int) -> int:
    """按锚点换算：1000‰ ≡ velocity 64。"""
    return int(round(velocity / ANCHOR_VELOCITY * ANCHOR_PERMILLE))


# 等级 → permille（由上面的换算得出，不手写死值以免两处漂移）
PERMILLE = {k: velocity_to_permille(v) for k, v in VELOCITY.items()}


def level_to_permille(level: str) -> int:
    if level not in PERMILLE:
        raise KeyError(f"未知力度等级：{level!r}（允许 {sorted(PERMILLE)}）")
    return PERMILLE[level]


def permille_to_nearest_level(permille: int) -> tuple:
    """反查最近等级（仅用于界面回显；不得用于"猜测"来源等级）。"""
    best = min(PERMILLE.items(), key=lambda kv: abs(kv[1] - permille))
    return best[0], abs(best[1] - permille)


def table() -> dict:
    return dict(PERMILLE)
