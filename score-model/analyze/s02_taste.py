# -*- coding: utf-8 -*-
"""S02 品味学习（P9）：把"分析数据 + 评分"积累成可用的权重库。

目的：工具现在能**描述**一首曲子（密度/张力/推进/难度/扰动…），但判不了"好不好听"。
听感判断暂时只能来自大模型（以后来自人）。本模块把这两者接起来：

  1. `features_of(analysis)`：从 S02 分析结果里抽**固定特征向量**（可复现、可追溯）；
  2. 数据集：`inbox/dataset.jsonl`，一行 = 一次课业（run）+ 特征 + 评分；
  3. `train()`：岭回归拟合 `评分 ≈ w·特征`，用**留一法**给指标；
     样本不足时**明确拒绝训练**（返回 insufficient），不假装有结论；
  4. `predict()`：给分 + 每个特征的贡献（能回答"为什么这首分高/低"）；
  5. `export_weights()`：导出成 TOML，供 `s02 score` / `report` 等已有功能读取。

纪律：学出来的东西只是"当前数据下的偏好"，不是真理；样本量、留一法误差、覆盖度都要随模型一起保存。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

# 固定特征顺序（改顺序会使旧模型失效，所以写死并在模型里存一份）
FEATURES = (
    "notes",
    "num_sections",
    "num_phrases",
    "num_motifs",
    "num_variants",
    "repeat_ratio",
    "density_mean",
    "density_std",
    "density_max",
    "centroid_mean",
    "centroid_std",
    "span",
    "perturb_rate",
    "hard_rate",
    "tension_mean",
    "tension_std",
    "drive_mean",
    "space_mean",
    "bright_mean",
    "dim_spread",
    "motif_coverage",
)


def _stats(vals: list) -> tuple:
    if not vals:
        return 0.0, 0.0
    mu = sum(vals) / len(vals)
    var = sum((v - mu) ** 2 for v in vals) / len(vals)
    return mu, math.sqrt(var)


def features_of(analysis: dict) -> dict:
    """S02 视图（`s02_api.payload` 的结果）→ 固定特征向量。"""
    s = analysis.get("summary") or {}
    secs = analysis.get("sections") or []
    windows = analysis.get("windows") or []
    motifs = analysis.get("motifs") or []
    variants = analysis.get("variants") or []
    pert = (analysis.get("perturbations") or {}).get("events") or []

    dens = [float(w.get("density") or 0.0) for w in windows]
    cent = [float(w.get("centroid") or 0.0) for w in windows]
    hard = [float(w.get("hard") or 0.0) for w in windows]
    tens = [float((x.get("dims") or {}).get("tension") or 0.0) for x in secs]
    drive = [float((x.get("dims") or {}).get("drive") or 0.0) for x in secs]
    space = [float((x.get("dims") or {}).get("space") or 0.0) for x in secs]
    bright = [float((x.get("dims") or {}).get("bright") or 0.0) for x in secs]

    d_mu, d_sd = _stats(dens)
    c_mu, c_sd = _stats(cent)
    t_mu, t_sd = _stats(tens)
    notes = int(s.get("notes") or 0)
    pitch_range = s.get("pitch_range") or [0, 0]

    covered = 0
    for m in motifs:
        covered += int(m.get("length") or 0) * int(m.get("count") or 0)

    def avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "notes": float(notes),
        "num_sections": float(len(secs)),
        "num_phrases": float(len(analysis.get("phrases") or [])),
        "num_motifs": float(len(motifs)),
        "num_variants": float(len(variants)),
        "repeat_ratio": float(s.get("repeat_ratio") or 0.0),
        "density_mean": round(d_mu, 4),
        "density_std": round(d_sd, 4),
        "density_max": round(max(dens) if dens else 0.0, 4),
        "centroid_mean": round(c_mu, 4),
        "centroid_std": round(c_sd, 4),
        "span": float((pitch_range[1] - pitch_range[0]) if len(pitch_range) == 2 else 0),
        "perturb_rate": round(len(pert) / notes, 4) if notes else 0.0,
        "hard_rate": round(sum(1 for h in hard if h > 0) / max(1, len(hard)), 4),
        "tension_mean": round(t_mu, 4),
        "tension_std": round(t_sd, 4),
        "drive_mean": round(avg(drive), 4),
        "space_mean": round(avg(space), 4),
        "bright_mean": round(avg(bright), 4),
        "dim_spread": round(float(np.std([avg(tens), avg(drive), avg(space), avg(bright)]))
                             if secs else 0.0, 4),
        "motif_coverage": round(covered / notes, 4) if notes else 0.0,
    }


# ── 数据集 ────────────────────────────────────────────

def load_dataset(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_row(path, row: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_dataset(path, rows: list) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")


# ── 训练 ──────────────────────────────────────────────

def _matrix(rows: list):
    X = np.array([[float(r["features"].get(k, 0.0)) for k in FEATURES] for r in rows])
    y = np.array([float(r["overall"]) for r in rows])
    return X, y


def _zscore(X):
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    return (X - mu) / sd, mu, sd


def _fit(Xz, y, alpha: float):
    """带截距的岭回归：先把 y 中心化，再解 (XᵀX+αI)w = Xᵀ(y−ȳ)。"""
    d = Xz.shape[1]
    y_mu = float(y.mean())
    A = Xz.T @ Xz + alpha * np.eye(d)
    b = Xz.T @ (y - y_mu)
    return np.linalg.solve(A, b), y_mu


def train(rows: list, *, min_samples: int = 12, alpha: float = 1.0) -> dict:
    """岭回归 + 留一法。样本不足时返回 {"insufficient": True, ...}，不硬训。"""
    rows = [r for r in rows if r.get("overall") is not None]
    n = len(rows)
    if n < min_samples:
        return {"insufficient": True, "samples": n, "min_samples": min_samples,
                "reason": f"样本 {n} < 最小 {min_samples}；继续积累（每次 flow run + taste rate 都会加一行）"}
    X, y = _matrix(rows)
    Xz, mu, sd = _zscore(X)
    w, y_mu = _fit(Xz, y, alpha)

    # 留一法
    loo_pred = []
    for i in range(n):
        idx = [j for j in range(n) if j != i]
        w_i, y_mu_i = _fit(Xz[idx], y[idx], alpha)
        loo_pred.append(float(Xz[i] @ w_i + y_mu_i))
    loo_pred = np.array(loo_pred)
    ss_res = float(((y - loo_pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-9
    r2 = 1.0 - ss_res / ss_tot
    mae = float(np.abs(y - loo_pred).mean())

    return {
        "insufficient": False,
        "features": list(FEATURES),
        "mean": mu.tolist(),
        "scale": sd.tolist(),
        "weights": w.tolist(),
        "y_mean": round(y_mu, 6),
        "alpha": alpha,
        "samples": n,
        "metrics": {"loo_r2": round(r2, 4), "loo_mae": round(mae, 4)},
    }


def predict(model: dict, features: dict) -> dict:
    """给分 + 每个特征的贡献（原始单位≈标准化后 × 权重）。"""
    if model.get("insufficient") or "weights" not in model:
        raise ValueError("模型不可用（样本不足或未训练）")
    names = model["features"]
    x = np.array([float(features.get(k, 0.0)) for k in names])
    z = (x - np.array(model["mean"])) / np.array(model["scale"])
    w = np.array(model["weights"])
    contrib = z * w
    base = float(model.get("y_mean", 0.0))
    raw = float(base + z @ w)
    return {
        "score": round(raw, 4),
        "score_clamped": round(min(1.0, max(0.0, raw)), 4),
        "base": round(base, 4),
        "contributions": sorted(
            ({"feature": names[i], "value": round(float(x[i]), 4),
              "contrib": round(float(contrib[i]), 4)} for i in range(len(names))),
            key=lambda d: -abs(d["contrib"])),
    }


def save_model(model: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_model(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def export_weights(model: dict) -> dict:
    """给已有功能用的权重（标准化空间，可直接算一个"品味分"）。"""
    if model.get("insufficient"):
        raise ValueError("模型不可用，无法导出权重")
    return {
        "features": model["features"],
        "mean": model["mean"],
        "scale": model["scale"],
        "weights": model["weights"],
        "meta": {"samples": model["samples"], "loo_r2": model["metrics"]["loo_r2"],
                 "loo_mae": model["metrics"]["loo_mae"]},
    }


# ── 评分（大模型先打，人以后打）──────────────────────

def rate(path, run_id: str, *, overall: float, dims: dict | None = None,
         scorer: str = "llm", model: str = "", note: str = "") -> dict:
    """给一次 run 打分：overall 0..1（其余维度可选），写回数据集该行。"""
    if not (0.0 <= float(overall) <= 1.0):
        raise ValueError("overall 必须在 0..1")
    rows = load_dataset(path)
    hit = None
    for r in rows:
        if r.get("run_id") == run_id:
            hit = r
            break
    if hit is None:
        raise ValueError(f"数据集里没有这次 run：{run_id}（先 flow run）")
    rec = {"scorer": scorer, "model": model, "overall": float(overall),
           "dims": dims or {}, "note": note,
           "at": __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
    hit["overall"] = float(overall)
    hit["dims"] = dims or {}
    hit.setdefault("ratings", []).append(rec)
    write_dataset(path, rows)
    return hit


def rated(rows: list) -> list:
    return [r for r in rows if r.get("overall") is not None]


def stats(rows: list) -> dict:
    rated_rows = rated(rows)
    return {
        "runs": len(rows),
        "rated": len(rated_rows),
        "unrated": len(rows) - len(rated_rows),
        "by_scorer": {},
        "overall_mean": round(sum(r["overall"] for r in rated_rows) / len(rated_rows), 3)
        if rated_rows else None,
    }
