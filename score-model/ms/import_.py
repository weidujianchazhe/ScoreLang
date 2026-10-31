# -*- coding: utf-8 -*-
"""MS 导入（门面）。真正实现：`importers/ms_import.py` / `ms_import_midi.py`。

统一返回 `(MSDocument, report)`；report 里带"缺口"（导入时丢掉了什么）。
"""
from __future__ import annotations

from pathlib import Path

from ms_import import import_musicxml  # noqa: F401
from ms_import_midi import import_midi as _import_midi_bytes  # noqa: F401


def import_midi(path_or_bytes, *, max_pianos: int = 2):
    """MIDI 文件路径或字节 → (MSDocument, report)。"""
    data = (Path(path_or_bytes).read_bytes()
            if isinstance(path_or_bytes, (str, Path)) else bytes(path_or_bytes))
    return _import_midi_bytes(data, max_pianos=max_pianos)


__all__ = ["import_midi", "import_musicxml"]
