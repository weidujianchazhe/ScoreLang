# -*- coding: utf-8 -*-
"""S02 参照比较（P12）：不给分，只给"在参照集里的位置（分位数）"。

管理者指出的原则：S02 是**翻译/测量层**，不该有"评分"。
所以：
  · 单曲 → 给测量值（0..1 是公式归一后的位置，不是打分）；
  · 跨曲 → 给**分位数**：本曲某项指标在参照集里排第几（0–100%），
    以及参照集的 p25 / p50 / p75。
这样"比较"就有数（"我们的密度在参照集里排 92%"），但不会造出一个"质量分"。

用法：
    mscli s02 compare 曲.ms --refs <参照目录>     # 目录里放 .ms / .s02
    mscli s02 compare 曲.ms --batch ref-classical # 或用 library 里已有的批次
"""
from __future__ import annotations

import json
from pathlib import Path

import s02_api
import s02_quality


def _metrics_of(score) -> dict:
    payload = s02_api.build_payload(score)
    return s02_quality.analyze(payload)["metrics"]


def refs_from_dir(dir_path) -> list:
    """参照目录里的 .ms / .s02 → [{name, metrics}]。"""
    out = []
    root = Path(dir_path)
    for p in sorted(root.glob("*.s02")) + sorted(root.glob("*.ms")):
        try:
            if p.suffix == ".s02":
                import s02_io
                score = s02_io.parse(p.read_text(encoding="utf-8"))
            else:
                import ms_io
                from ms_to_s02 import to_s02
                score, _ = to_s02(ms_io.load(p), time_base_us=500_000)
            out.append({"name": p.stem, "metrics": _metrics_of(score)})
        except Exception as e:  # noqa: BLE001
            out.append({"name": p.stem, "error": str(e)[:80]})
    return out


def refs_from_batch(batch_dir) -> list:
    """从 inbox/batches/<tag>/index.json 反查每个 run 的 analysis.json。"""
    idx_path = Path(batch_dir) / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    out = []
    for r in idx.get("runs", []):
        run_dir = Path(r["run_dir"])
        ap = run_dir / "analysis.json"
        try:
            payload = json.loads(ap.read_text(encoding="utf-8"))
            out.append({"name": r.get("source") or run_dir.name,
                        "metrics": s02_quality.analyze(payload)["metrics"]})
        except Exception as e:  # noqa: BLE001
            out.append({"name": run_dir.name, "error": str(e)[:80]})
    return out


def _pct(vals: list, q: float) -> float:
    if not vals:
        return 0.0
    vs = sorted(vals)
    k = (len(vs) - 1) * q
    lo, hi = int(k), min(len(vs) - 1, int(k) + 1)
    frac = k - lo
    return round(vs[lo] * (1 - frac) + vs[hi] * frac, 3)


def compare(piece_metrics: dict, refs: list) -> dict:
    """每项指标：本曲值 + 参照集分位（0–100）+ p25/p50/p75。"""
    rows = {}
    for metric in s02_quality.METRICS:
        mine = piece_metrics.get(metric)
        vals = [r["metrics"].get(metric) for r in refs
                if r.get("metrics", {}).get(metric) is not None]
        if mine is None or not vals:
            rows[metric] = {"value": mine, "percentile": None, "n": len(vals)}
            continue
        below = sum(1 for v in vals if v < mine)
        equal = sum(1 for v in vals if v == mine)
        pct = round(100.0 * (below + 0.5 * equal) / len(vals), 0)
        rows[metric] = {
            "value": mine,
            "percentile": pct,
            "n": len(vals),
            "ref": {"p25": _pct(vals, 0.25), "p50": _pct(vals, 0.50),
                    "p75": _pct(vals, 0.75),
                    "min": round(min(vals), 3), "max": round(max(vals), 3)},
        }
    return {"metrics": rows, "ref_count": len(refs),
            "note": "分位数只说明'在参照集里排第几'；高/低哪个好，取决于参照集和作品意图。"}


def to_text(res: dict) -> str:
    lines = [f"参照集 {res['ref_count']} 首；分位 = 本曲在该指标上的位置（0–100%）", "",
             "指标            本曲   分位   参照 p25 / p50 / p75"]
    for metric, row in res["metrics"].items():
        v = "—" if row["value"] is None else f"{row['value']:.2f}"
        p = "—" if row["percentile"] is None else f"{row['percentile']:>.0f}%"
        if row.get("ref"):
            r = row["ref"]
            ref = f"{r['p25']:.2f} / {r['p50']:.2f} / {r['p75']:.2f}"
        else:
            ref = "—"
        lines.append(f"  {metric:14s} {v:>5s} {p:>5s}   {ref}")
    lines += ["", res["note"]]
    return "\n".join(lines)
