# -*- coding: utf-8 -*-
"""检查参考文档是否与 Python 注册表漂移。

用法：python tools/check_reference_docs.py
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reference"
meta_path = OUT / "_meta.json"
if not meta_path.exists():
    print("缺 _meta.json：先跑 tools/gen_reference_docs.py")
    raise SystemExit(1)
meta = json.loads(meta_path.read_text(encoding="utf-8"))
bad = []
for rel, digest in meta.get("sources", {}).items():
    p = ROOT / rel
    if not p.exists():
        bad.append(f"源文件缺失：{rel}")
        continue
    now = hashlib.sha256(p.read_bytes()).hexdigest()
    if now != digest:
        bad.append(f"源已变：{rel}")
for name in meta.get("files", []):
    if not (OUT / name).exists():
        bad.append(f"文档缺失：{name}")
if bad:
    print("参考文档漂移：")
    for x in bad:
        print("  -", x)
    print("请重跑：python tools/gen_reference_docs.py")
    raise SystemExit(1)
print("参考文档一致（源哈希 + 文件齐全）")
