# -*- coding: utf-8 -*-
"""快检：只跑与近期改动最相关、且执行快的套件（日常用，收尾再跑全量）。

用法：
    python tools/verify_fast.py            # 快检
    python tools/verify_fast.py --list     # 看清单
说明：输出只有汇总与失败项，避免把长日志灌进上下文。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNT_RE = re.compile(r"共\s*(\d+)\s*项：通过\s*(\d+)，失败\s*(\d+)")

SUITES = [
    "tests/ms_engine_test.py",
    "tests/mscli_smoke_test.py",
    "tests/diagnose_test.py",
    "tests/ms_fix_test.py",
    "tests/export_check_test.py",
    "tests/release_test.py",
    "tests/s02_quality_test.py",
    "tests/s02_sync_test.py",
]


def main(argv: list) -> int:
    if "--list" in argv:
        for s in SUITES:
            print(s)
        return 0
    env = dict(__import__("os").environ, PYTHONIOENCODING="utf-8")
    total_checks = 0
    failures = []
    print(f"快检：{len(SUITES)} 套件（失败才展开）")
    for name in SUITES:
        p = ROOT / name
        if not p.exists():
            failures.append((name, "缺失"))
            continue
        r = subprocess.run([sys.executable, "-B", str(p)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900, env=env)
        out = (r.stdout or "") + (r.stderr or "")
        m = COUNT_RE.search(out)
        n = int(m.group(1)) if m else None
        passed = int(m.group(2)) if m else None
        if r.returncode != 0 or (m and int(m.group(3)) > 0):
            tail = "\n".join(out.strip().splitlines()[-12:])
            failures.append((name, tail))
        else:
            total_checks += n or 0
    if failures:
        print(f"\n失败 {len(failures)} 项：")
        for name, why in failures:
            print(f"  - {name}:\n{why}")
        return 1
    print(f"快检通过（{len(SUITES)} 套件，{total_checks} 项断言）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
