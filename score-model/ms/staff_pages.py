# -*- coding: utf-8 -*-
"""兼容 shim：五线谱分页已迁到 render/ms_staff_pages.py（呈现层）。"""
from ms_staff_pages import pages, svg_pages_to_png  # noqa: F401

__all__ = ["pages", "svg_pages_to_png"]
