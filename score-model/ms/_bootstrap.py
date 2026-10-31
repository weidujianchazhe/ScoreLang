# -*- coding: utf-8 -*-
"""把模块目录接进 sys.path（过渡方案；最终目标是包内相对导入）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _d in ("ms/_core", "perform", "render", "audio", "analyze", "importers"):
    _p = ROOT / _d
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
