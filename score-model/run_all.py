# -*- coding: utf-8 -*-
"""统一测试入口（排表 I-1）。

一条命令跑全部套件，输出「套件 / 期望 / 实际 / 结果」，任一失败或**项数不符**即非零退出。

用法：
    python run_all.py              # 跑全部
    python run_all.py --list       # 只列套件与期望项数
    python run_all.py --filter ms_ # 只跑名字含 ms_ 的

设计要点：
  - 强制 UTF-8（否则 transform_core_smoke 会因 `↔` 报 GBK 错，属环境伪失败）
  - **项数校验**：只判"没崩"不够，项数变少可能是断言被删
  - 每个套件独立子进程，互不影响退出码
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COUNT_RE = re.compile(r"共\s*(\d+)\s*项：通过\s*(\d+)，失败\s*(\d+)")

# (套件名, 期望项数)  期望 None = 只判退出码（兼容套件不输出项数）
SUITES = [
    # 新事件模型线
    ("tests/ms_events_test.py", 21),
    ("tests/ms_io_test.py", 17),
    ("tests/ms_audio_semantics_test.py", 9),
    ("tests/ms_playability_test.py", 8),
    ("tests/s02_sync_test.py", 11),
    ("tests/curves_test.py", 5),
    ("tests/turns_test.py", 11),
    ("tests/vocal_test.py", 19),

    ("tests/vocal_write_test.py", 35),
    ("tests/pedals_instrument_test.py", 31),
    ("tests/release_test.py", 17),
    ("tests/performance_test.py", 29),
    ("tests/instrument_actions_test.py", 18),
    ("tests/notation_map_test.py", 15),
    ("tests/midi_actions_test.py", 7),
    ("tests/s02_io_test.py", 16),
    ("tests/s02_probe_test.py", 17),
    ("tests/s02_index_test.py", 30),
    ("tests/s02_harmony_test.py", 14),
    ("tests/s02_segment_test.py", 17),
    ("tests/s02_baseline_test.py", 10),
    ("tests/s02_fingering_test.py", 14),
    ("tests/s02_perturb_test.py", 14),
    ("tests/s02_score_test.py", 14),
    ("tests/s02_calibrate_test.py", 14),
    ("tests/s02_frontend_test.py", 24),
    ("tests/s02_incremental_test.py", 11),
    ("tests/s02_bench_test.py", 6),
    ("tests/s02_diff_test.py", 16),
    ("tests/s02_refs_test.py", 15),
    ("tests/audio_cli_test.py", 5),
    ("tests/msflow_test.py", 10),
    ("tests/s02_taste_test.py", 24),
    ("tests/s02_quality_test.py", 13),
    ("tests/s02_capability_test.py", 17),
    ("tests/s02_compare_test.py", 10),
    ("tests/segments_test.py", 7),
    ("tests/ms_midi_multi_test.py", 13),
    ("tests/ms_engine_test.py", 25),
    ("tests/ms_edit_test.py", 30),
    ("tests/ms_dynamics_levels_test.py", 18),
    ("tests/ms_articulation_test.py", 19),
    ("tests/ms_ornament_test.py", 33),
    ("tests/ms_author_test.py", 40),
    ("tests/ms_structure_allows_test.py", 13),
    ("tests/ms_samples_test.py", 17),
    ("tests/ms_render_options_test.py", 22),
    ("tests/ms_render_jianpu_test.py", 18),
    ("tests/ms_midi_test.py", 28),
    ("tests/ms_cli_test.py", 17),
    ("tests/ms_audio_backend_test.py", 13),
    ("tests/ms_render_staff2_test.py", 17),
    ("tests/ms_undo_test.py", 20),
    ("tests/ms_to_s02_test.py", 21),
    ("tests/transform_events_test.py", 16),
    ("tests/ms_edit_batch_test.py", 25),
    ("tests/render_snapshot_test.py", None),
    ("tests/ms_server_test.py", 21),
    ("check_consistency.py", None),
    ("check_structure.py", None),
    ("tests/ms_debt_test.py", 10),
    ("tests/ms_import_test.py", 19),
    ("tests/r6_roundtrip_test.py", 20),
    ("tests/r1r5_design_test.py", 17),
    ("tests/render_realization_test.py", 16),
    ("scripts/perf_baseline.py", None),
    ("tests/ms_score_test.py", 15),
    # 旧字段表线（C2/C3 依赖，冻结）
    ("tests/c3_judgment_test.py", None),
    ("tests/c3_redteam_a.py", None),
    ("tests/c3_verify_narrow.py", None),
    ("tests/g2_construction.py", None),
    ("tests/test_v02_acceptance.py", None),
    ("tests/mscli_smoke_test.py", 27),
    ("tests/ms_fix_test.py", 22),
    ("tests/diagnose_test.py", 18),
    ("tests/ms_md_test.py", 28),
    ("tests/textfmt_test.py", 16),
    ("tests/export_check_test.py", 13),
]

# 已知：这个脚本有自己的预期问题（硬编码旧 SHA），单独标注，不算新失败
KNOWN_ISSUES = {
    "c3_verify_fi1_fix.py": "硬编码 transform_core SHA 基线（V4-1），属预存问题，未纳入套件清单",
}


def run_one(script: str) -> tuple:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", script],
        cwd=str(HERE), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = COUNT_RE.search(out)
    total = int(m.group(1)) if m else None
    passed = int(m.group(2)) if m else None
    tail = ""
    if not m:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        tail = lines[-1][:60] if lines else ""
    return proc.returncode, total, passed, tail


def main(argv: list) -> int:
    if "--list" in argv:
        for name, expected in SUITES:
            print(f"{name:34} 期望 {expected if expected is not None else '（仅退出码）'}")
        return 0

    quiet = "--quiet" in argv
    filt = None
    if "--filter" in argv:
        i = argv.index("--filter")
        filt = argv[i + 1] if i + 1 < len(argv) else None

    suites = [(n, e) for n, e in SUITES if not filt or filt in n]
    if not quiet:
        print(f"运行 {len(suites)} 个套件（UTF-8 强制）\n" + "-" * 74)
    rows, failures = [], []
    for name, expected in suites:
        code, total, passed, tail = run_one(name)
        if code != 0:
            status = "FAIL"
            failures.append((name, f"退出码 {code}", tail))
        elif expected is not None and total != expected:
            status = "COUNT?"
            failures.append((name, f"项数 {total} ≠ 期望 {expected}", ""))
        else:
            status = "ok"
        rows.append((name, expected, total, passed, status))

    if not quiet:
        for name, expected, total, passed, status in rows:
            exp = expected if expected is not None else "-"
            act = f"{total}" if total is not None else "-"
            print(f"{name:34} 期望 {exp:>4}  实际 {act:>4}  "
                  f"通过 {passed if passed is not None else '-':>4}  {status}")
    print("-" * 74)

    if failures:
        if quiet:
            print("-" * 74)
        print(f"\n失败 {len(failures)} 项：")
        for name, why, tail in failures:
            print(f"  - {name}: {why}" + (f"  [{tail}]" if tail else ""))
        print("\n提示：已知预存问题（不计入本清单）：")
        for k, v in KNOWN_ISSUES.items():
            print(f"  - {k}: {v}")
        return 1

    total_checks = sum(t for _, _, t, _, _ in rows if t)
    print(f"全部通过（{len(rows)} 套件，{total_checks} 项断言）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
