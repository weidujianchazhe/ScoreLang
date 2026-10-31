# -*- coding: utf-8 -*-
"""P7 增量索引：只重算改动过的旋律线，其余复用上一版 `.s02x`。

为什么能增量：动机是**逐旋律线**发现的（乐器+声部），一条线的改动不会影响
另一条线的动机；变体扫描也只扫母动机自己那条线。所以：

  · 线签名（token 序列哈希）没变的线 → 直接复用其动机与变体；
  · 变了的线 → 只重算这条线；
  · 边/特征/段落仍整体重算（它们便宜，且跨线）。

用法：
    idx = s02_incremental.update(old_idx_or_path, new_score)   # 原地重写 .s02x
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import s02_index


def line_sigs(score) -> dict:
    """每条旋律线的签名：{ "inst|voice": sha1(tokens) }。"""
    out = {}
    for key, notes in s02_index._lines(score).items():
        toks = s02_index._tokens(notes)
        raw = json.dumps(toks, ensure_ascii=False).encode("utf-8")
        out[f"{key[0]}|{key[1]}"] = hashlib.sha1(raw).hexdigest()[:16]
    return out


def _copy_motif(m) -> "s02_index.Motif":
    return copy.deepcopy(m)


def update(target, new_score) -> dict:
    """`target` 可为旧的 idx dict 或 `.s02x` 路径；返回新 idx（并重写文件）。"""
    is_path = isinstance(target, (str, os.PathLike))
    path = Path(target) if is_path else None
    prev = s02_index.read_index(path) if is_path else target
    new = s02_index.build(new_score, prev=prev)
    stats = {
        "lines_total": len(new.get("line_sig") or {}),
        "lines_reused": new.get("_reused_lines", 0),
        "lines_rebuilt": new.get("_rebuilt_lines", 0),
        "motifs_reused": new.get("_reused_motifs", 0),
        "motifs_total": len(new["motifs"]),
    }
    if path is not None:
        s02_index.save(new, path, meta={"line_sig": json.dumps(new.get("line_sig") or {},
                                                               ensure_ascii=False)})
    return {"index": new, "stats": stats}
