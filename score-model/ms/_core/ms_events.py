# -*- coding: utf-8 -*-
"""MS（聚合入口）。

实现分层：
  · `ms_model`       — 纯数据（dataclass + 常量）
  · `ms_validate`    — 结构校验 V1–V13
  · `ms_realization` — 演奏收束 R-1..R-4

本模块只做**同名再导出**，旧调用（`ev.validate` / `ev.Event`）保持可用。
"""
from ms_model import *  # noqa: F401,F403
from ms_validate import validate  # noqa: F401
from ms_realization import check_realization  # noqa: F401
