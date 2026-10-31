# -*- coding: utf-8 -*-
"""S02 性能基线（P7）：把各层的耗时量出来，落成可复跑的表。

用法：
    python scripts/s02_bench.py --time-base 500000 a.ms b.ms [--json out.json]
"""
from __future__ import annotations

import json
import sys as _sys
import time
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import model_v02 as mv
import ms_io
import s02_api
import s02_fingering
import s02_harmony
import s02_index
import s02_perturb
import s02_probe
import s02_render
import s02_score
import s02_segment


def _time(fn):
    t = time.perf_counter()
    fn()
    return round(time.perf_counter() - t, 3)


def bench_doc(doc, *, time_base_us: int = 500_000) -> dict:
    """跑一遍所有层，返回 {layer: seconds, meta}。"""
    holder = {}

    def project():
        from ms_to_s02 import to_s02
        holder["score"], _ = to_s02(doc, time_base_us=time_base_us)

    t_project = _time(project)
    score = holder["score"]
    seg_holder = {}

    def do_segment():
        seg_holder["seg"] = s02_segment.segment(score)

    def do_index():
        seg_holder["idx"] = s02_index.build(score)

    rows = {
        "notes": len(score.notes),
        "project": t_project,
        "probe": _time(lambda: s02_probe.analyze(score)),
        "harmony": _time(lambda: s02_harmony.analyze(score)),
        "perturb": _time(lambda: s02_perturb.analyze(score)),
        "fingering": _time(lambda: s02_fingering.analyze(score)),
        "segment": _time(do_segment),
        "index": _time(do_index),
        "report": _time(lambda: __import__("s02_report").build(score, title="bench")),
        "render_svg": _time(lambda: s02_render.render(score)),
        "score_dims": _time(lambda: s02_score.analyze(score)),
    }
    # 增量：改一个音后重算
    import copy
    changed = copy.deepcopy(score)
    if changed.notes:
        p = changed.notes[-1].pitch
        changed.notes[-1].pitch = type(p)(p.step, p.alter, p.octave + 1)
    idx = seg_holder.get("idx")
    if idx:
        rows["index_incremental"] = _time(lambda: s02_index.build(changed, prev=idx))
    rows["api"] = _time(lambda: {"n": len(seg_holder["seg"]["sections"])})
    return rows


def run(files: list, *, time_base_us: int = 500_000) -> list:
    out = []
    for f in files:
        p = _Path(f)
        doc = ms_io.load(p)
        row = bench_doc(doc, time_base_us=time_base_us)
        row["file"] = p.name
        out.append(row)
    return out


def to_markdown(rows: list) -> str:
    cols = ["notes", "project", "probe", "harmony", "perturb", "fingering",
            "segment", "index", "index_incremental", "report", "render_svg"]
    lines = ["# S02 性能基线", "",
             "| 曲目 | " + " | ".join(cols) + " |",
             "|---" * (len(cols) + 1) + "|"]
    for r in rows:
        cells = [str(r.get(c, "-")) for c in cols]
        lines.append(f"| {r['file']} | " + " | ".join(cells) + " |")
    lines += ["", "> 单位：秒。`index_incremental` = 改一个音后的重算耗时。"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    args = _sys.argv[1:]
    tb = 500_000
    if "--time-base" in args:
        i = args.index("--time-base")
        tb = int(args[i + 1])
        del args[i:i + 2]
    out_json = None
    if "--json" in args:
        i = args.index("--json")
        out_json = args[i + 1]
        del args[i:i + 2]
    rows = run(args, time_base_us=tb)
    print(to_markdown(rows))
    if out_json:
        _Path(out_json).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
