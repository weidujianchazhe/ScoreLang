# -*- coding: utf-8 -*-
"""出图（工程外转发壳）：`.ms` → SVG。

真正的实现在 `../score-model/tools/render_svg.py`，这里只做转发，
保证旧命令 `python tools/render_svg.py ...` 继续可用，且不写死任何绝对路径
（工程目录整体搬走后仍然有效）。
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "score-model"
TARGET = ENGINE / "tools" / "render_svg.py"

if not TARGET.exists():
    print(f"找不到引擎渲染器：{TARGET}", file=sys.stderr)
    print("（若只搬走了 score-model，请直接用 score-model/tools/render_svg.py）",
          file=sys.stderr)
    raise SystemExit(2)

runpy.run_path(str(TARGET), run_name="__main__")
