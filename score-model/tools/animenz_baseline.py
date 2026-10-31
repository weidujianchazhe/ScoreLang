# -*- coding: utf-8 -*-
"""A 叔（Animenz）参照基线：用已转的钢琴曲做 S02 判定基准。

输出：
  inbox/s02/animenz_baseline.json   每个测量量的参考区间（min/p25/median/p75/max）
  inbox/s02/animenz_report.md       每首对基线的位置 + 说明

用法：
  python tools/animenz_baseline.py
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "inbox" / "s02"

FIELDS = [
    # 质量指标
    "counterpoint", "dynamics", "ending", "ending_voices", "harmonic",
    "phrasing", "playability", "register", "return", "structure", "variety",
]


def _percentile(vals, p):
    s = sorted(vals)
    if not s:
        return None
    k = max(0, min(len(s) - 1, int(round((len(s) - 1) * p))))
    return s[k]


def _rank(vals, v):
    """v 在 vals 中的百分位（0..100）。"""
    if not vals:
        return None
    below = sum(1 for x in vals if x < v)
    equal = sum(1 for x in vals if x == v)
    return round((below + 0.5 * equal) / len(vals) * 100, 1)


def collect(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    notes = max(1, int((d.get("summary") or {}).get("notes") or 1))
    m = (d.get("quality") or {}).get("metrics") or {}
    meas = (d.get("quality") or {}).get("measurements") or {}
    out = {k: m.get(k) for k in FIELDS}
    td = (meas.get("technique_density") or {}).get("per_note")
    out["technique_density"] = td
    out["motif_cover"] = d.get("motif_note_coverage")
    out["motifs_per_1000"] = round(len(d.get("motifs") or []) / notes * 1000, 3)
    out["variants_per_1000"] = round(len(d.get("variants") or []) / notes * 1000, 3)
    out["sections"] = len(d.get("sections") or [])
    ek = d.get("edges_by_kind") or {}
    for k in ("next", "similar", "variant"):
        out[f"edges_{k}_per_1000"] = round(ek.get(k, 0) / notes * 1000, 3)
    vs = d.get("variants") or []
    for kind in ("inversion", "retrograde", "rhythmic"):
        c = sum(1 for v in vs if v.get("kind") == kind)
        out[f"var_{kind}_ratio"] = round(c / len(vs), 3) if vs else None
    dims = d.get("sections") or []
    for k in ("tension", "drive", "space", "bright"):
        vals = [(s.get(k) or 0) for s in dims]
        out[f"sec_{k}_mean"] = round(sum(vals) / len(vals), 3) if vals else None
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--suffix", default="v2")
    args = ap.parse_args()
    files = sorted(SRC.glob("*.json"))
    files = [f for f in files if "baseline" not in f.name
             and not any(e in f.stem for e in args.exclude)]
    rows = {}
    for f in files:
        try:
            rows[f.stem] = collect(f)
        except Exception as exc:  # noqa: BLE001
            print("跳过", f.name, exc)
    if not rows:
        print("没有数据")
        return 1

    baseline = {}
    for k in sorted({k for r in rows.values() for k in r}):
        vals = [r[k] for r in rows.values() if isinstance(r.get(k), (int, float))]
        if not vals:
            continue
        baseline[k] = {
            "n": len(vals), "min": min(vals), "p25": _percentile(vals, .25),
            "median": st.median(vals), "p75": _percentile(vals, .75),
            "max": max(vals), "mean": round(st.mean(vals), 4),
        }
    (SRC / f"animenz_baseline_{args.suffix}.json").write_text(
        json.dumps({"source": "Animenz 钢琴改编（OMR 转换；v2 排除低置信曲目）",
                    "instrument": "grand piano (horizontal / Steinway-type)",
                    "note": "卧式三角琴（Steinway 类）/Animenz 风格，小样本（n=5）参考区间；不是绝对评分，其他乐器不直接套用",
                    "n_songs": len(rows), "baseline": baseline},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# A 叔（Animenz）卧式三角琴（Steinway 类）参照基线", "",
             f"样本：{len(rows)} 首；**小样本参考区间**，用于判断“像不像 A 叔这类复杂钢琴改编”，",
             "不是绝对好听分数。", "",
             "| 测量量 | 基线中位 | 区间 min–max | " +
             " | ".join(rows) + " |", "|---|---|---|" + "---|" * len(rows)]
    for k, b in baseline.items():
        cells = []
        for name, r in rows.items():
            v = r.get(k)
            cells.append("-" if v is None else str(v))
        lines.append(f"| {k} | {b['median']} | {b['min']}–{b['max']} | " +
                     " | ".join(cells) + " |")

    # 每首相对基线的位置
    lines += ["", "## 每首相对基线的位置（百分位 0–100）", ""]
    for name, r in rows.items():
        lines += [f"### {name}", "",
                  "| 测量量 | 值 | 基线中位 | 百分位 | 位置 |", "|---|---|---|---|---|"]
        for k, b in baseline.items():
            v = r.get(k)
            if not isinstance(v, (int, float)):
                continue
            vals = [rr.get(k) for rr in rows.values()
                    if isinstance(rr.get(k), (int, float))]
            pct = _rank(vals, v)
            if b["min"] <= v <= b["max"]:
                pos = "区间内"
            elif v > b["max"]:
                pos = "高于基线"
            else:
                pos = "低于基线"
            lines.append(f"| {k} | {v} | {b['median']} | {pct} | {pos} |")
        lines.append("")
    lines += ["", "## 使用说明", "",
              "1. 只对**钢琴复杂改编**有意义；换乐器需要另建基线。",
              "2. n=5 太小，本基线只用于“风格参考/异常筛查”，不用于最终评分。",
              "3. OMR 错的音会污染基线；先校谱再定稿。",
              "4. 区间外不必然是问题，结合段落/动机/可弹性一起看。"]
    (SRC / f"animenz_report_{args.suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("写出：", SRC / "animenz_baseline_{args.suffix}.json", SRC / "animenz_report_{args.suffix}.md")
    for k in ("playability", "structure", "motif_cover", "variants_per_1000"):
        if k in baseline:
            b = baseline[k]
            print(f"  {k}: 中位 {b['median']}  区间 {b['min']}–{b['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
