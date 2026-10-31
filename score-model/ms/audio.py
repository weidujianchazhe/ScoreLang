# -*- coding: utf-8 -*-
"""MS 音频（门面）。真正实现：`audio/make_audio.py`。

声音只由 MS 乐谱模型决定；S02 不参与（这是引擎铁律）。
"""
from __future__ import annotations

from pathlib import Path

from make_audio import render as samples, write_wav  # noqa: F401


def to_wav(doc, path, *, tail: float = 0.8) -> Path:
    """doc → WAV 文件（唯一会写音频的入口）。"""
    data = samples(doc, tail=tail)
    write_wav(data, path)
    return Path(path)


__all__ = ["samples", "write_wav", "to_wav"]
