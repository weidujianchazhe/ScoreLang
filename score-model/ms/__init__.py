# -*- coding: utf-8 -*-
"""乐谱模型：写乐谱的库。

首次使用先跑 `ms.selfcheck()`（技能包自检；红则按提示修复）。

用任务脚本写谱，直接导出 ABC 谱 / 五线谱 / 音频。
包名是 `ms`（即“乐谱模型”）；主要写法：`ms.start(...)` 逐步填：

    import ms
    g = ms.start(bpm=96, instruments=[{"type": "piano"}])
    g.notes(["C4@0+1/mf", "D4@1+1"])   # 逐步填；也可 ms.build(spec) 整份提交
    song = g.finish()
    print(song.export_abc())      # ABC 谱
    print(song.export_staff())    # 五线谱
    song.export_wav("out.wav")    # 音频

写之前先读 `ms.prime()`（全部可选乐器 + 能写哪些演奏 + 怎么写）；
数据字典：`ms.schema_text()`；可选乐器：`ms.instruments()`。
"""
from __future__ import annotations

from . import _bootstrap  # noqa: F401  （先把内部目录接进 sys.path）

VERSION = "ms-1.0.0"
SCHEMA = "ms-1"

from . import api, registry  # noqa: E402
from .api import *  # noqa: F401,F403,E402

__all__ = ["VERSION", "SCHEMA", "api", "registry", *api.__all__]
