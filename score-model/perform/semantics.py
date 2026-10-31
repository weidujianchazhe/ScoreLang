# -*- coding: utf-8 -*-
"""演奏语义数据（唯一权威）：奏法参数、装饰音参数、转折瞬态。

只放**数据**；行为在 ms_articulation / ms_ornament / ms_performance。
"""
from __future__ import annotations

# 奏法：时值/力度修正（千分比）
ARTICULATIONS = {
    "staccato":      {"gate_pm": 500,  "vel_pm": 1000, "src": "MuseScore instruments.xml"},
    "staccatissimo": {"gate_pm": 330,  "vel_pm": 1000, "src": "MuseScore instruments.xml"},
    "tenuto":        {"gate_pm": 1000, "vel_pm": 1000, "src": "MuseScore instruments.xml"},
    "marcato":       {"gate_pm": 670,  "vel_pm": 1200, "src": "MuseScore instruments.xml"},
    "accent":        {"gate_pm": 1000, "vel_pm": 1200, "src": "约定（仪器文件无独立定义）"},
}

# 装饰音展开参数
GRACE_SHORT_PM = 250
APPOGGIATURA_LONG_PM = 500
MORDENT_AUX_PM = 100
TURN_EACH_PM = 150
TRILL_RATE_HZ = 10

# 转折瞬态：None = 无瞬态（只作结构/连奏标记）
TURN_TRANSIENT = {
    "bow_change": dict(kind="friction", sec=0.030, gain=0.09, band=0.55),
    "breath":     dict(kind="air", sec=0.045, gain=0.07, band=0.15),
    "mallet":     dict(kind="wood", sec=0.025, gain=0.10, band=0.30),
    "retrigger":  dict(kind="click", sec=0.012, gain=0.08, band=0.85),
    "restrike":   dict(kind="click", sec=0.010, gain=0.07, band=0.95),
    "key_noise":  dict(kind="click", sec=0.020, gain=0.04, band=0.60),
    "key_click":  dict(kind="click", sec=0.014, gain=0.05, band=0.90),
    "inhale":     dict(kind="air", sec=0.120, gain=0.05, band=0.10),
    "col_legno":  dict(kind="wood", sec=0.020, gain=0.12, band=0.45),
    "brush":      dict(kind="friction", sec=0.060, gain=0.06, band=0.25),
    "rim_shot":   dict(kind="click", sec=0.018, gain=0.12, band=0.75),
    "liaison":    None,
    "break":      None,
}
