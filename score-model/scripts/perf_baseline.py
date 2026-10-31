# -*- coding: utf-8 -*-
"""性能基线（分级）。

为什么分级：
  - **快档**要进 `run_all`（每次提交都跑），必须几秒内完成 → 只跑 1k / 5k
  - **全量**要跑 20k 才能看到大对象/GC 现象，但耗时 ~30s → 手动/定期
  - 平方级退化在 **5k/1k 的比值**上就会暴露（线性≈5，平方≈25），
    所以快档不必跑 20k 也能抓住"写成了平方"

用法：
    python perf_baseline.py            # 快档（默认）：1k/5k + 阈值断言，写 PERF.md
    python perf_baseline.py --full     # 全量：+ 20k 与内存峰值，写 PERF.md
    python perf_baseline.py --tier soak --n 100000   # 浸泡档（手动，看 GC/内存）

阈值设计：**抓数量级，不抓 10% 波动**（慢机器不误报）。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import argparse
import time
import tracemalloc
from pathlib import Path

import ms_audio as au
import ms_events as ev
import ms_io as mj
import ms_midi as mm
import ms_render as rd
import ms_render_jianpu as jp
import ms_render as ro
import ms_render_staff2 as st
import ms_semantics as ms
import ms_to_s02 as conv

HERE = ROOT
TB = 500_000
OPTS = ro.RenderOptions(meter=(4, 4), time_base_us=TB, clef="treble")

# 快档：进 run_all 的规模与阈值（宽松，只抓数量级）
FAST_SIZES = (1_000, 5_000)
# 全量：额外的规模
FULL_SIZES = (20_000,)

# (操作名, 阈值秒, 说明) —— 5k 规模下的绝对上限
FAST_CEILINGS = [
    ("validate", 0.500, "5k 事件 validate"),
    ("json_dumps", 3.000, "5k 事件 JSON 写出"),
    ("json_loads", 3.000, "5k 事件 JSON 读入"),
    ("render_staff2", 4.000, "5k 事件五线渲染"),
    ("to_s02", 3.000, "5k 事件投影"),
]
# 比值上限：5k / 1k。线性≈5，平方≈25；取 15 留余量
RATIO_MAX = 15.0


def make_doc(n: int) -> "ev.MSDocument":
    base = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0),
            6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}
    events = []
    for i in range(n):
        semi = 48 + (i * 7) % 36
        step, alter = base[semi % 12]
        events.append(ev.Event(
            id=f"n{i}", instrument_id=1, onset_us=i * 250_000,
            pitch=ev.Pitch(step, alter, semi // 12 - 1, semi),
            release_us=i * 250_000 + 250_000, release_state="given",
            dynamics=ev.Dynamics(ms.VALUE, 1000 + (i % 7) * 100, "relative_permille", "cal", "measured")))
    return ev.MSDocument(events=events)


def timeit(fn, repeat=1):
    best = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best


def measure(n: int, *, repeat: int = 2, mem: bool = False) -> dict:
    doc = make_doc(n)
    text = mj.dumps(doc)
    row = {"n": n, "bytes": len(text.encode("utf-8"))}
    row["validate"] = timeit(lambda: ev.validate(doc), repeat)
    row["json_dumps"] = timeit(lambda: mj.dumps(doc), repeat)
    row["json_loads"] = timeit(lambda: mj.loads(text), repeat)
    row["render_pianoroll"] = timeit(lambda: rd.render_pianoroll(doc, options=OPTS), 1)
    row["render_staff2"] = timeit(lambda: st.render_staff2(doc, OPTS), 1)
    row["render_jianpu"] = timeit(lambda: jp.render_jianpu(doc, OPTS, mode="melody"), 1)
    row["midi_export"] = timeit(lambda: mm.write_midi(doc, time_base_us=TB), 1)
    row["audio_params"] = timeit(lambda: au.event_parameters(doc), 1)
    row["to_s02"] = timeit(lambda: conv.to_s02(doc, time_base_us=TB), 1)

    # 内存峰值：只在全量/浸泡档测（tracemalloc 会显著拖慢快档）
    if mem:
        tracemalloc.start()
        mj.dumps(doc)
        peak_dump = tracemalloc.get_traced_memory()[1]
        tracemalloc.reset_peak()
        st.render_staff2(doc, OPTS)
        peak_render = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        row["peak_json_mb"] = peak_dump / 1e6
        row["peak_render_mb"] = peak_render / 1e6
    return row


COLS = ["validate", "json_dumps", "json_loads", "render_pianoroll", "render_staff2",
        "render_jianpu", "midi_export", "audio_params", "to_s02"]


def render_table(rows: list) -> str:
    head = f"{'事件数':>7} {'JSON字节':>10} " + " ".join(f"{c:>15}" for c in COLS)
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(f"{r['n']:>7} {r['bytes']:>10} " +
                     " ".join(f"{r[c]*1000:>13.1f}ms" for c in COLS))
    return "\n".join(lines)


def check_fast(rows: list) -> list:
    """快档断言：绝对上限 + 5k/1k 比值。返回问题列表（空=通过）。"""
    problems = []
    small, mid = rows[0], rows[1]
    for op, ceiling, label in FAST_CEILINGS:
        if mid[op] > ceiling:
            problems.append(f"{label} = {mid[op]*1000:.0f}ms > {ceiling*1000:.0f}ms")
    for op in COLS:
        a, b = small[op], mid[op]
        if a <= 0:
            continue
        ratio = b / a
        if ratio > RATIO_MAX:
            problems.append(f"{op} 的 5k/1k 比值 {ratio:.1f} > {RATIO_MAX}"
                            f"（线性≈5，平方≈25 → 疑似超线性）")
    return problems


def write_report(rows: list, tier: str, problems: list, mem: bool) -> None:
    md = ["# 性能基线（PERF）", "",
          f"> 生成：`python perf_baseline.py`（tier={tier}）；纯 Python 单线程；"
          "用于发现**数量级**退化，不是绝对指标。", "",
          "## 分级", "",
          "| 档 | 规模 | 何时跑 | 能抓什么 |", "|---|---|---|---|",
          "| **fast** | 1k / 5k | 每次 `run_all` | 绝对上限 + 超线性（5k/1k 比值） |",
          "| **full** | 1k / 5k / 20k | 手动 / 定期 | 大对象、渲染与 JSON 的规模效应 |",
          "| **soak** | 自定义（如 100k） | 手动 | GC、内存峰值、长时间行为 |",
          "", "## 何时跑全量（触发条件，非日历）", "",
          "| 触发 | 为什么 | 跑哪档 |", "|---|---|---|",
          "| 改了**规模相关**代码（渲染循环 / 序列化 / 投影 / 校验） | 这类改动最容易引入 O(n²) | **full** |",
          "| 发布 / 里程碑前 | 一次性确认规模效应 | **full** |",
          "| 要提高支持的事件上限（如 20k→100k） | GC 与内存峰值只有大档看得见 | **soak** |",
          "| 用户报「大谱卡 / 崩」 | 需要定位是时间还是内存 | **full → soak** |",
          "| 每 N 次提交（建议 N=10）或每周 | 快档只抓数量级，会漏缓变 | **full** |",
          "",
          "> 判据：**快档抓「写错了」（超线性），全量抓「规模效应」（内存/GC），浸泡抓「上限」。**",
          "", "## 结果", "", "```", render_table(rows), "```", ""]
    if mem:
        md += ["## 内存峰值（tracemalloc）", "",
               "| 事件数 | JSON 写出 | 五线渲染 |", "|---|---|---|"]
        for r in rows:
            md.append(f"| {r['n']} | {r['peak_json_mb']:.1f} MB | {r['peak_render_mb']:.1f} MB |")
        md.append("")
    if problems:
        md += ["## 问题（超阈值）", ""] + [f"- {p}" for p in problems] + [""]
    else:
        md += ["## 结论", "", f"- 各操作在 {rows[-1]['n']} 事件规模下均在阈值内。", ""]
    (HERE / "PERF.md").write_text("\n".join(md), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="加跑 20k 与内存峰值")
    ap.add_argument("--tier", choices=("fast", "full", "soak"), default=None)
    ap.add_argument("--n", type=int, default=100_000, help="soak 档的规模")
    args = ap.parse_args(argv)

    tier = args.tier or ("full" if args.full else "fast")
    sizes = list(FAST_SIZES) + (list(FULL_SIZES) if tier in ("full", "soak") else [])
    if tier == "soak":
        sizes = list(FAST_SIZES) + list(FULL_SIZES) + [args.n]

    rows = []
    for n in sizes:
        print(f"测 {n} 事件…")
        rows.append(measure(n, repeat=1 if n >= 20_000 else 2, mem=(tier in ("full", "soak"))))

    print(render_table(rows))
    problems = check_fast(rows) if tier == "fast" else []
    if tier == "full":
        big = rows[-1]
        if big["validate"] > 5.0:
            problems.append(f"validate 在 20k 下 {big['validate']:.1f}s（>5s）")
        if big["json_dumps"] > 10.0:
            problems.append(f"json_dumps 在 20k 下 {big['json_dumps']:.1f}s（>10s）")

    write_report(rows, tier, problems, mem=tier in ("full", "soak"))
    print(f"\n已写 {HERE / 'PERF.md'}")
    if problems:
        print("问题：")
        for p in problems:
            print("  -", p)
        return 1
    print(f"快档断言通过（档位 {tier}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
