# -*- coding: utf-8 -*-
"""对照 A 叔基线：给新生成/新写的曲子做“像不像 A 叔”的判定数据。

用法：
    python tools/baseline_compare.py --spec task.json
    python tools/baseline_compare.py --ms piece.ms
    python tools/baseline_compare.py --md piece.md
    （默认基线：inbox/s02/animenz_baseline_v3.json）

输出：每个测量量的值 / 基线中位 / 区间 / 百分位 / 位置（区间内/高/低）。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms", "ms/_core", "perform", "render",
                                       "audio", "analyze", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms  # noqa: E402
import ms_io  # noqa: E402
import ms_md  # noqa: E402
from ms.task import Song  # noqa: E402
import s02_analyze  # noqa: E402
import animenz_baseline as ab  # noqa: E402


def load_song(arg: dict) -> Song:
    if arg.get("spec"):
        return ms.build(json.loads(Path(arg["spec"]).read_text(encoding="utf-8")))
    if arg.get("ms"):
        doc = ms_io.load(arg["ms"])
        return Song(doc, bpm=float(arg.get("bpm") or 120), meter=(4, 4))
    if arg.get("md"):
        txt = Path(arg["md"]).read_text(encoding="utf-8")
        return ms_md.compile_song(txt)
    raise SystemExit("需要 --spec / --ms / --md 之一")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--ms")
    ap.add_argument("--md")
    ap.add_argument("--bpm", type=float)
    ap.add_argument("--baseline",
                    default=str(ROOT / "inbox" / "s02" / "animenz_baseline_v3.json"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))["baseline"]
    song = load_song(vars(args))
    with tempfile.TemporaryDirectory() as td:
        ms_path = Path(td) / "x.ms"
        ms_io.save(song._doc, str(ms_path))
        data = s02_analyze.analyze(ms_path)
        jf = Path(td) / "x.json"
        jf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        vals = ab.collect(jf)
    rows = []
    for k, b in base.items():
        v = vals.get(k)
        if not isinstance(v, (int, float)):
            continue
        vals_all = [v]
        status = "区间内" if b["min"] <= v <= b["max"] else (
            "高于" if v > b["max"] else "低于")
        rows.append({"field": k, "value": v, "median": b["median"],
                     "min": b["min"], "max": b["max"], "status": status})
    if args.json:
        print(json.dumps({"song": song.title or "generated", "rows": rows},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"对照基线：{Path(args.baseline).name}（n={json.loads(Path(args.baseline).read_text(encoding='utf-8'))['n_songs']}）")
    print("| 测量量 | 值 | 基线中位 | 区间 | 位置 |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['field']} | {r['value']} | {r['median']} | "
              f"{r['min']}–{r['max']} | {r['status']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
