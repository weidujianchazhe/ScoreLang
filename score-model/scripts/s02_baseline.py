# -*- coding: utf-8 -*-
"""基线分布：把若干首曲子跑成同一套特征，输出 JSON + 汇总表。

用途（`S02剩余任务清单.md` P0-2）：给"大数据校准"准备第 0 号样本——
先用现有成品建立"我们自己这批曲子长什么样"的基线。

用法：
    python scripts/s02_baseline.py out/inbox/baseline --time-base 500000 a.ms b.ms ...
"""
from __future__ import annotations

import json
import sys as _sys
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import s02_probe
import s02_segment
import s02_weights as wt


def analyze_doc(doc, *, time_base_us: int, grid: int = 480):
    """MS 乐谱模型 → (score, probe 结果, 分段结果)。"""
    import s02_harmony
    from ms_to_s02 import to_s02

    score, losses = to_s02(doc, time_base_us=time_base_us,
                           grid_units_per_quarter=grid)
    pr = s02_probe.analyze(score)
    # 把张力/跳进并进逐窗口表（与 s02_segment 的口径一致）
    hz = s02_harmony.analyze(score)
    by = {b["window"]: b for b in pr["bars"]}
    for h in hz.get("windows", []):
        if h["window"] in by:
            by[h["window"]].update({k: v for k, v in h.items() if k != "window"})
    seg = s02_segment.segment(score, weights=wt.load())
    return score, pr, seg, losses


def summarize(name: str, pr: dict, seg: dict) -> dict:
    s = pr["summary"]
    bars = pr["bars"]
    dens = [b["density"] for b in bars if b.get("density") is not None]
    cent = [b["centroid"] for b in bars if b.get("centroid") is not None]
    tens = [b.get("v_tension_mean") or 0.0 for b in bars]
    leaps = [b.get("leap_mean") or 0.0 for b in bars]
    return {
        "name": name,
        "notes": s["notes"],
        "windows": s["windows"],
        "sections": len(seg["sections"]),
        "phrases": len(seg["phrases"]),
        "density_mean": round(sum(dens) / len(dens), 2) if dens else 0.0,
        "density_max": round(max(dens), 2) if dens else 0.0,
        "centroid_mean": round(sum(cent) / len(cent), 1) if cent else 0.0,
        "tension_mean": round(sum(tens) / len(tens), 3) if tens else 0.0,
        "leap_mean": round(sum(leaps) / len(leaps), 3) if leaps else 0.0,
        "repeat_ratio": s["repeat_ratio"],
        "pitch_range": s["pitch_range"],
        "vel_range": s["vel_range"],
        "labels": [x["label"] for x in seg["sections"]],
    }


def write_summary(rows: list, outdir: _Path) -> _Path:
    lines = ["# S02 基线分布", "",
             "| 曲目 | 音符 | 窗口 | 段 | 句读 | 密度μ | 密度max | 音区μ | 张力μ | 跳进μ | 重复率 | 标签 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| {name} | {notes} | {windows} | {sections} | {phrases} | "
                     "{density_mean} | {density_max} | {centroid_mean} | {tension_mean} | "
                     "{leap_mean} | {repeat_ratio:.0%} | {labels} |".format(**r))
    lines += ["", "> 由 `scripts/s02_baseline.py` 生成；数值口径见 `S02索引与计算.md`。"]
    p = outdir / "summary.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def run(paths: list, outdir, *, time_base_us: int, grid: int = 480) -> list:
    import ms_io

    out = _Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in paths:
        p = _Path(path)
        doc = ms_io.load(p)
        score, pr, seg, losses = analyze_doc(doc, time_base_us=time_base_us, grid=grid)
        name = p.stem
        (out / f"{name}.probe.json").write_text(
            json.dumps({"summary": pr["summary"], "bars": pr["bars"],
                        "segments": seg}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        rows.append(summarize(name, pr, seg))
    (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    write_summary(rows, out)
    return rows


if __name__ == "__main__":
    if len(_sys.argv) < 3:
        print("用法：s02_baseline.py <outdir> <file.ms>... [--time-base N]")
        raise SystemExit(2)
    args = _sys.argv[1:]
    tb = 500_000
    if "--time-base" in args:
        i = args.index("--time-base")
        tb = int(args[i + 1])
        del args[i:i + 2]
    rows = run(args[1:], args[0], time_base_us=tb)
    for r in rows:
        print(f"{r['name']}: {r['notes']} 音 / {r['sections']} 段 / 密度μ {r['density_mean']}"
              f" / 重复率 {r['repeat_ratio']:.0%}")
