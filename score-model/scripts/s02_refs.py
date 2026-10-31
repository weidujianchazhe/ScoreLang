# -*- coding: utf-8 -*-
"""参照曲目库（P8-3）：把"样本不够"变成一个可积累、可复核的流程。

目录约定（默认 `score-model/references/`）：
    references/
      manifest.toml            # 每首曲子的登记（文件、标题、加入日期）
      *.ms                     # 参照曲目本身
      weights.latest.toml      # 当前最新校准结果
      weights.YYYYMMDD-NNN.toml# 兼容版本（不覆盖）
      calibration_log.md       # 每次校准一行：样本数 / 阈值 / 留一法漂移 / 判断

为什么要有留一法：5 首时阈值会漂 ±20–40%；只有把这个漂移量记下来，
才能回答"样本够不够、能不能信"。
"""
from __future__ import annotations

import datetime as _dt
import shutil
import sys as _sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("core", "notation", "transform", "audio", "render", "tools", "importers", "perform", "analyze", "ms/_core", "scripts"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ms_io
import s02_calibrate as cal
import s02_weights as wt

DEFAULT_DIR = ROOT / "references"
# 生成的日志/报告属于"产出"，按工程区约定写到 ../inbox（工程区不设 docs 之外的游离文档）
DEFAULT_OUT = ROOT.parent / "inbox" / "calibration"


def _ensure(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root


def manifest_path(root: Path) -> Path:
    return root / "manifest.toml"


def load_manifest(root=None) -> list:
    root = _ensure(Path(root or DEFAULT_DIR))
    p = manifest_path(root)
    if not p.exists():
        return []
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return list(data.get("piece") or [])


def save_manifest(entries: list, root=None) -> Path:
    root = _ensure(Path(root or DEFAULT_DIR))
    lines = ["# 参照曲目登记（每首一行 [[piece]]）"]
    for e in entries:
        lines += ["", "[[piece]]",
                  f'file = "{e["file"]}"',
                  f'title = "{e.get("title", "")}"',
                  f'added = "{e.get("added", "")}"']
    p = manifest_path(root)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def add(path, *, title: str = "", root=None, time_base_us: int = 500_000) -> dict:
    """登记一首参照曲目：校验能解析 → 复制进 references/ → 写 manifest。"""
    root = _ensure(Path(root or DEFAULT_DIR))
    src = Path(path)
    doc = ms_io.load(src)                      # 解析失败会直接抛，不进库
    if not doc.events:
        raise ValueError(f"{src.name} 里没有事件，不能当参照")
    dst = root / src.name
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    entries = [e for e in load_manifest(root) if e.get("file") != dst.name]
    entry = {"file": dst.name, "title": title or src.stem,
             "added": _dt.date.today().isoformat()}
    entries.append(entry)
    entries.sort(key=lambda e: e["file"])
    save_manifest(entries, root)
    n_notes = len(doc.events)
    return {**entry, "notes": n_notes}


def list_pieces(root=None) -> list:
    root = _ensure(Path(root or DEFAULT_DIR))
    out = []
    for e in load_manifest(root):
        p = root / e["file"]
        out.append({**e, "exists": p.exists()})
    return out


def _load_scores(root: Path, time_base_us: int):
    from ms_to_s02 import to_s02

    scores, names = [], []
    for e in load_manifest(root):
        p = root / e["file"]
        if not p.exists():
            continue
        doc = ms_io.load(p)
        scores.append(to_s02(doc, time_base_us=time_base_us)[0])
        names.append(e["file"])
    return names, scores


def calibrate(*, root=None, time_base_us: int = 500_000, today: str | None = None,
              out_dir=None) -> dict:
    """跑校准 + 留一法稳定性 + 版本化落盘 + 记日志。"""
    root = _ensure(Path(root or DEFAULT_DIR))
    out = Path(out_dir) if out_dir else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    names, scores = _load_scores(root, time_base_us)
    if not scores:
        raise ValueError("references/ 里还没有登记任何曲子，先 s02 refs --add <file.ms>")
    derived = cal.derive(cal.collect(scores))
    today = today or _dt.date.today().strftime("%Y%m%d")

    # 留一法：逐首拿掉，看关键阈值漂多少
    loo = []
    for i in range(len(scores)):
        rest = [s for j, s in enumerate(scores) if j != i]
        if not rest:
            continue
        d = cal.derive(cal.collect(rest))
        loo.append({
            "removed": names[i],
            "density_high": d["label"]["density_high"],
            "tension_high": d["label"]["tension_high"],
        })
    base_d = derived["label"]["density_high"]
    base_t = derived["label"]["tension_high"]
    max_drift_d = max((abs(x["density_high"] - base_d) for x in loo), default=0.0)
    max_drift_t = max((abs(x["tension_high"] - base_t) for x in loo), default=0.0)
    rel_d = max_drift_d / base_d if base_d else 0.0
    # 判断：漂移 >20% 就认为样本不足
    enough = rel_d <= 0.20
    verdict = "样本基本够（漂移 ≤20%）" if enough else "样本不足（漂移 >20%，继续积累）"

    stamp = f"{today}-{len(scores):03d}"
    versioned = root / f"weights.{stamp}.toml"
    cal.write_toml(derived, versioned, meta={
        "pieces": len(scores), "samples": derived["stats"]["samples"],
        "date": today, "loo_max_drift_density": round(max_drift_d, 2)})
    latest = root / "weights.latest.toml"
    shutil.copy2(versioned, latest)

    log = out / "calibration_log.md"
    head = ("# 校准日志\n\n| 日期 | 曲目数 | 窗口数 | 密度低/高 | 张力低/高 | 留一法最大漂移 | 判断 | 版本文件 |\n"
            "|---|---|---|---|---|---|---|---|\n")
    if not log.exists():
        log.write_text(head, encoding="utf-8")
    row = (f"| {today} | {len(scores)} | {derived['stats']['samples']} | "
           f"{derived['label']['density_low']}/{base_d} | "
           f"{derived['label']['tension_low']}/{base_t} | "
           f"密度 {max_drift_d:.2f}（{rel_d:.0%}）、张力 {max_drift_t:.3f} | "
           f"{verdict} | {versioned.name} |\n")
    with log.open("a", encoding="utf-8") as f:
        f.write(row)

    report = out / f"calibration_{stamp}.md"
    cal.report(derived, current=wt.load(), path=report)
    return {
        "pieces": len(scores), "samples": derived["stats"]["samples"],
        "label": derived["label"], "score": derived["score"],
        "loo": loo, "loo_max_drift": {"density": round(max_drift_d, 3),
                                      "tension": round(max_drift_t, 4),
                                      "density_rel": round(rel_d, 3)},
        "verdict": verdict, "enough": enough,
        "versioned": str(versioned), "latest": str(latest),
        "report": str(report), "log": str(log),
    }
