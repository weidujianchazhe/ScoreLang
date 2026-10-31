# -*- coding: utf-8 -*-
"""兼容 shim：ABC 导出已迁到 render/ms_abc.py（呈现层）。"""
from ms_abc import to_abc  # noqa: F401

__all__ = ["to_abc"]
