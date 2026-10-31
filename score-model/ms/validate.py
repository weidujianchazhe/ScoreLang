# -*- coding: utf-8 -*-
"""MS 校验（门面 re-export）。真正实现：`core/ms_validate.py`。

包含两道闸：
  · `validate(doc)`：结构/物理合法性（V1–V19），返回错误列表；
  · `pedal_diagnostics(doc)`：踏板链与"实际发声总长"（V4c 的数据层）。
"""
from __future__ import annotations

from ms_validate import (  # noqa: F401
    validate, pedal_diagnostics, PEDAL_CHAIN_WARN_US, PEDAL_CHAIN_MAX_US,
)

__all__ = ["validate", "pedal_diagnostics", "PEDAL_CHAIN_WARN_US",
           "PEDAL_CHAIN_MAX_US"]
