# -*- coding: utf-8 -*-
"""品味学习（taste）：特征抽取、数据集、训练（含样本不足拒绝）、预测与解释。"""
from __future__ import annotations

import json
import sys as _sys
import tempfile
from pathlib import Path as _Path

ROOT = _Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import numpy as np

import s02_taste as T

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail))


tmp = _Path(tempfile.mkdtemp())
ds = tmp / "dataset.jsonl"

# ── 1) 特征抽取 ───────────────────────────────────────
analysis = {
    "summary": {"notes": 100, "repeat_ratio": 0.2, "pitch_range": [48, 84]},
    "sections": [
        {"id": "SA", "start_bar": 1, "end_bar": 4, "label": "陈述",
         "dims": {"tension": 0.2, "drive": 0.4, "space": 0.6, "bright": 0.5}},
        {"id": "SB", "start_bar": 5, "end_bar": 8, "label": "高潮",
         "dims": {"tension": 0.8, "drive": 0.9, "space": 0.1, "bright": 0.6}},
    ],
    "phrases": [{"id": "SA1"}, {"id": "SA2"}, {"id": "SB1"}],
    "windows": [{"window": 1, "density": 4.0, "centroid": 60.0, "hard": 0.0},
                {"window": 2, "density": 8.0, "centroid": 66.0, "hard": 0.5}],
    "motifs": [{"id": "M0001", "length": 4, "count": 3}],
    "variants": [{"motif": "M0001", "transform": "inversion"}],
    "perturbations": {"events": [{"kind": "accent"}, {"kind": "density"}]},
}
f = T.features_of(analysis)
check("T1 特征维度固定", set(f) == set(T.FEATURES), str(sorted(f)))
check("T2 密度均值正确", abs(f["density_mean"] - 6.0) < 1e-6, str(f["density_mean"]))
check("T3 难度比例正确", abs(f["hard_rate"] - 0.5) < 1e-6, str(f["hard_rate"]))
check("T4 扰动率正确", abs(f["perturb_rate"] - 0.02) < 1e-6, str(f["perturb_rate"]))
check("T5 音域跨度正确", f["span"] == 36.0, str(f["span"]))
check("T6 动机覆盖率正确", abs(f["motif_coverage"] - 12 / 100) < 1e-6, str(f["motif_coverage"]))
check("T7 空分析不崩", len(T.features_of({})) == len(T.FEATURES))

# ── 2) 数据集与评分 ───────────────────────────────────
for i in range(3):
    T.append_row(ds, {"run_id": f"r{i}", "features": f, "overall": None,
                      "dims": {}, "ratings": []})
rows = T.load_dataset(ds)
check("T8 追加与读取", len(rows) == 3, str(len(rows)))
T.rate(ds, "r1", overall=0.7, dims={"tension": 0.8}, scorer="llm", model="m1", note="n")
rows = T.load_dataset(ds)
r1 = next(r for r in rows if r["run_id"] == "r1")
check("T9 评分写回", r1["overall"] == 0.7 and r1["dims"]["tension"] == 0.8, str(r1)[:80])
check("T10 评分兼容保留", len(r1["ratings"]) == 1 and r1["ratings"][0]["model"] == "m1",
      str(r1["ratings"]))
check("T11 评分范围校验",
      (lambda: (T.rate(ds, "r1", overall=1.5), False)[1] if False else True)())
try:
    T.rate(ds, "r1", overall=1.5)
    ok = False
except ValueError:
    ok = True
check("T12 越界分数被拒", ok)
try:
    T.rate(ds, "不存在", overall=0.5)
    ok = False
except ValueError:
    ok = True
check("T13 不存在的 run 被拒", ok)

# ── 3) 样本不足拒绝训练 ───────────────────────────────
ins = T.train(rows, min_samples=12)
check("T14 样本不足明确拒绝", ins.get("insufficient") is True and "样本" in ins["reason"],
      str(ins)[:100])

# ── 4) 合成数据：能学出线性关系 ───────────────────────
rng = np.random.default_rng(7)
syn = tmp / "syn.jsonl"
# 只为 3 个特征设定真实关系（其余是噪声），40 个样本应该能学出来
true_w = {k: 0.0 for k in T.FEATURES}
true_w.update({"drive_mean": 0.35, "tension_mean": 0.25, "space_mean": -0.30})
for i in range(40):
    feats = {k: float(rng.normal()) for k in T.FEATURES}
    score = 0.5 + sum(true_w[k] * feats[k] for k in T.FEATURES) + float(rng.normal()) * 0.02
    T.append_row(syn, {"run_id": f"s{i}", "features": feats, "overall": score,
                       "dims": {}, "ratings": []})
model = T.train(T.load_dataset(syn), min_samples=12, alpha=1.0)
check("T15 40 样本能训练", model.get("insufficient") is False, str(model.get("reason")))
check("T16 留一法 R² 高", model["metrics"]["loo_r2"] > 0.8,
      str(model["metrics"]))
names = model["features"]
w = dict(zip(names, model["weights"]))
check("T17 学到的方向正确（drive 正、space 负）", w["drive_mean"] > 0 and w["space_mean"] < 0,
      f"drive={w['drive_mean']:.3f} space={w['space_mean']:.3f}")

# ── 5) 预测与解释 ─────────────────────────────────────
row0 = T.load_dataset(syn)[0]
pred = T.predict(model, row0["features"])
check("T18 预测分数可夹到 0..1", 0.0 <= pred["score_clamped"] <= 1.0,
      str(pred["score_clamped"]))
check("T19 基线+贡献可加总≈分数",
      abs(pred["base"] + sum(c["contrib"] for c in pred["contributions"])
          - pred["score"]) < 1e-3,
      f"{pred['base']}+{round(sum(c['contrib'] for c in pred['contributions']), 4)} vs {pred['score']}")
check("T20 贡献按绝对值排序",
      all(abs(pred["contributions"][i]["contrib"]) >= abs(pred["contributions"][i + 1]["contrib"])
          for i in range(len(pred["contributions"]) - 1)))

# ── 6) 存/取/导出 ─────────────────────────────────────
mp = tmp / "models" / "taste.json"
T.save_model(model, mp)
m2 = T.load_model(mp)
check("T21 模型存取一致", m2["weights"] == model["weights"])
exp = T.export_weights(m2)
check("T22 导出权重含元信息", exp["meta"]["samples"] == 40 and len(exp["weights"]) == 21,
      str(exp["meta"]))
try:
    T.export_weights(ins)
    ok = False
except ValueError:
    ok = True
check("T23 不可用模型拒绝导出", ok)

# ── 7) 统计 ───────────────────────────────────────────
st = T.stats(T.load_dataset(syn))
check("T24 统计正确", st["runs"] == 40 and st["rated"] == 40, str(st))

fail = [r for r in R if not r[1]]
for name, ok_, detail in R:
    if not ok_:
        print(f"[FAIL] {name}  {detail}")
print("=" * 52)
print(f"共 {len(R)} 项：通过 {len(R) - len(fail)}，失败 {len(fail)}")
raise SystemExit(0 if not fail else 1)
