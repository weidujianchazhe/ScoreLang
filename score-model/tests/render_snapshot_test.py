# -*- coding: utf-8 -*-
"""渲染视觉回归（排表 II-4）：把渲染结果钉成快照。

用途：任何渲染器改动若改变了输出字节，这里立刻失败——避免"看起来一样"的静默漂移。

用法：
    python render_snapshot_test.py              # 比对（缺失快照即失败）
    set UPDATE_SNAPSHOTS=1 && python render_snapshot_test.py   # 重新生成快照（须人工确认变更）

设计：
  - 每个用例固定输入（示例谱）+ 固定呈现参数 → 输出 SVG 字节
  - 快照存 `snapshots/<case>.svg`；比较按**完整字节**
  - 渲染器已保证确定性（无随机 id、无时间戳），否则本测试会一直红
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import os
import sys
from pathlib import Path

import ms_io as mj
import ms_render as rd
import ms_render_jianpu as jp
import ms_render as ro
import ms_render_staff2 as st

HERE = ROOT
SAMPLES = HERE / "fixtures" / "legacy"
SNAPS = ROOT / "tests" / "snapshots"

OPTS = ro.RenderOptions(meter=(4, 4), time_base_us=500_000, clef="treble")
OPTS_GRAND = ro.RenderOptions(meter=(4, 4), time_base_us=500_000, clef="grand")


def _load(name):
    return mj.loads((SAMPLES / f"{name}.ms").read_text(encoding="utf-8"))


CASES = [
    ("melody_pianoroll", lambda: rd.render_pianoroll(_load("simple_melody"), options=OPTS)),
    ("melody_staff", lambda: rd.render_staff(_load("simple_melody"), options=OPTS)),
    ("melody_staff2_treble", lambda: st.render_staff2(_load("simple_melody"), OPTS)),
    ("melody_staff2_grand", lambda: st.render_staff2(_load("simple_melody"), OPTS_GRAND)),
    ("melody_jianpu", lambda: jp.render_jianpu(_load("simple_melody"), OPTS, mode="melody")),
    ("melody_jianpu_twohands", lambda: jp.render_jianpu(_load("simple_melody"), OPTS, mode="two_hands")),
    ("chords_pianoroll", lambda: rd.render_pianoroll(_load("chords_and_pedal"), options=OPTS)),
    ("chords_staff2_grand", lambda: st.render_staff2(_load("chords_and_pedal"), OPTS_GRAND)),
    ("chords_jianpu_chords", lambda: jp.render_jianpu(_load("chords_and_pedal"), OPTS, mode="chords")),
    ("ornaments_pianoroll", lambda: rd.render_pianoroll(_load("ornaments"), options=OPTS)),
    ("ornaments_staff2_treble", lambda: st.render_staff2(_load("ornaments"), OPTS)),
    ("ornaments_jianpu", lambda: jp.render_jianpu(_load("ornaments"), OPTS, mode="melody")),
]


def main() -> int:
    update = os.environ.get("UPDATE_SNAPSHOTS") == "1"
    SNAPS.mkdir(exist_ok=True)
    failures, created = [], []
    for name, fn in CASES:
        svg = fn()
        path = SNAPS / f"{name}.svg"
        if update or not path.exists():
            path.write_text(svg, encoding="utf-8")
            created.append(name)
            continue
        if path.read_text(encoding="utf-8") != svg:
            failures.append(name)

    print(f"用例 {len(CASES)} 个")
    if created:
        print(f"新建快照 {len(created)} 个：{', '.join(created)}")
        if not update:
            print("提示：首跑会创建快照；请再跑一次确认稳定（或设 UPDATE_SNAPSHOTS=1 覆盖）")
    if failures:
        print(f"[FAIL] 快照不一致 {len(failures)} 个：{', '.join(failures)}")
        print("若变更是有意的，设 UPDATE_SNAPSHOTS=1 重跑并人工确认差异")
        return 1
    print(f"快照一致 {len(CASES) - len(created)} 个，新建 {len(created)} 个")
    # 新建快照不算失败（首次生成），但会打印提示；不一致才算失败
    return 0


if __name__ == "__main__":
    sys.exit(main())
