# -*- coding: utf-8 -*-
"""MS 读写（门面 re-export）。真正实现：`core/ms_io.py`。

`load(path)` 得到内存里的 `MSDocument`；`save(doc, path)` 才落盘。
**内存对象是工作态，文件只是序列化**——同一份 doc 可以直接交给 S02 分析，不必先写文件。
"""
from __future__ import annotations

from ms_io import load, save, dump, parse, fingerprint, iter_events  # noqa: F401

__all__ = ["load", "save", "dump", "parse", "fingerprint", "iter_events"]
