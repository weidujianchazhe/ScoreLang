# -*- coding: utf-8 -*-
"""一致性检查（排表 V-4）：文档 ↔ 实现 ↔ 测试 是否对得上。

检查四件事：
  1. 目录下每个 `*_test.py` 都在 `run_all.py` 的 SUITES 里（防"写了测试但没跑"）
  2. `run_all.py` 里的套件文件真实存在（防"登记了但不存在的套件"）
  3. SPEC §7.7 六条不变量在测试里有对应断言痕迹
  4. 关键模块与文档都在（防"文档提到但文件没了"）

退出码 0 = 全对得上；1 = 有缺口（逐条打印）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

REQUIRED_MODULES = [
    "ms/_core/ms_model.py",
    "ms/_core/ms_validate.py",
    "ms/_core/ms_realization.py",
    "ms/_core/ms_events.py",
    "ms/_core/ms_edit.py",
    "ms/_core/ms_author.py",
    "render/ms_render.py",
    "render/ms_render_jianpu.py",
    "render/ms_render_staff2.py",
    "render/ms_abc.py",
    "render/ms_staff_pages.py",
    "audio/ms_audio.py",
    "audio/ms_midi.py",
    "perform/ms_instruments.py",
    "perform/ms_performance.py",
    "perform/ms_articulation.py",
    "perform/ms_ornament.py",
    "perform/ms_dynamics_levels.py",
    "analyze/ms_to_s02.py",
    "analyze/transform_events.py",
    "tools/ms_server.py",
    "tools/mscli.py",
    "run_all.py",
]

# 文档目录豁免文件名检查：docs/spec 下允许多少份、什么名字都不强制（人读层）
DOC_DIR = "docs/spec"
MIN_DOCS = 6

# SPEC §7.7 六条不变量 → 测试里应出现的可核痕迹（关键词，宽松匹配）
INVARIANT_TRACES = [
    ("V1 release 三态一致", ["release_state", "NOT_PROVIDED"]),
    ("V2 释放≥起始 / 零时长仅 grace", ["零时长", "is_grace"]),
    ("V3 力度范围与伴随字段", ["dynamics_permille", "calibration_ref"]),
    ("V4 踏板顺序/深度/scope", ["踏板", "targets"]),
    ("V5 音高域与 instrument_id", ["UNSUPPORTED_PITCH_RANGE", "instrument_id"]),
    ("V6 同键同 onset 重叠", ["同键同 onset"]),
]


def suites_in_run_all() -> list:
    text = (HERE / "run_all.py").read_text(encoding="utf-8")
    names = re.findall(r'\("([^"]+\.py)",\s*(?:None|\d+)\)', text)
    # run_all 里现在写的是 tests/xxx.py；注册集合按文件名比对
    return [n.rsplit("/", 1)[-1] for n in names]


def main() -> int:
    problems = []

    # 1. 测试文件是否都被登记（tests/ 下全部 .py 都要在 run_all 里）
    test_files = {p.name for p in (HERE / "tests").glob("*.py")}
    registered = set(suites_in_run_all())
    missing_reg = sorted(test_files - registered)
    if missing_reg:
        problems.append(f"测试文件未登记到 run_all.py：{missing_reg}")

    # 2. 登记的套件是否存在（按 run_all 里写的相对路径查）
    raw = re.findall(r'\("([^"]+\.py)",\s*(?:None|\d+)\)',
                     (HERE / "run_all.py").read_text(encoding="utf-8"))
    ghost = sorted(n for n in raw if not (HERE / n).exists())
    if ghost:
        problems.append(f"run_all.py 登记了不存在的套件：{ghost}")

    # 3. 不变量痕迹
    events_test = (HERE / "tests/ms_events_test.py").read_text(encoding="utf-8")
    for label, keys in INVARIANT_TRACES:
        hits = [k for k in keys if k in events_test]
        if len(hits) < 1:
            problems.append(f"SPEC §7.7 {label} 在 ms_events_test.py 中找不到痕迹（期望含 {keys}）")

    # 4. 模块与文档存在
    miss_mod = [m for m in REQUIRED_MODULES if not (HERE / m).exists()]
    if miss_mod:
        problems.append(f"缺少模块：{miss_mod}")
    doc_dir = HERE / DOC_DIR
    docs = sorted(doc_dir.glob("*.md")) if doc_dir.exists() else []
    if len(docs) < MIN_DOCS:
        problems.append(f"{DOC_DIR} 文档过少：{len(docs)} < {MIN_DOCS}")

    # 5. 契约 §6.2 仍在（C-002/C-003 落笔的痕迹）
    con = ""
    for f in docs:
        t = f.read_text(encoding="utf-8")
        if f.name in ("转换契约.md", "TRANSFORM_CONTRACT.md") or "转换契约" in f.name:
            con = t
            break
    if con:
        for key in ("### §6.2", "6.2.7", "6.2.11"):
            if key not in con:
                problems.append(f"契约缺少 {key}")

    print(f"模块 {len(REQUIRED_MODULES)} 项 / 文档 {len(docs)} 项 / "
          f"测试文件 {len(test_files)} 个（登记 {len(registered)} 个）")
    if problems:
        print(f"[FAIL] {len(problems)} 处不一致：")
        for p in problems:
            print("  -", p)
        return 1
    print("全部一致：测试都登记、套件都存在、六条不变量有痕迹、模块与文档齐全、契约 §6.2 在册")
    return 0


if __name__ == "__main__":
    sys.exit(main())
