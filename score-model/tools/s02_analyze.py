# -*- coding: utf-8 -*-
"""S02 结构/依附关系分析：把转出的 MS 当作判定数据。

对每首：
  · 质量测量（quality.metrics / measurements）
  · 段落四维（tension/drive/space/bright）+ 句读
  · 动机 / 变体（s02_index）
  · 依附关系边（next / similar / variant / same-onset / pedal / turn）
输出：
  inbox/s02/<曲名>.json   单曲数据
  inbox/s02/summary.md    汇总表
  inbox/s02/edges_<曲名>.csv  关系边（供图计算/判定用）

用法：
    python tools/s02_analyze.py --dir inbox/omr_batch
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, *(ROOT / _d for _d in ("ms", "ms/_core", "perform", "render",
                                       "audio", "analyze", "importers", "tools"))):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ms  # noqa: E402
import ms_io  # noqa: E402
import s02_api  # noqa: E402
import s02_index  # noqa: E402
from ms_to_s02 import to_s02  # noqa: E402
from ms.task import Song  # noqa: E402


def _bpm_for(ms_path: Path) -> float:
    md = ms_path.with_suffix(".md")
    if md.exists():
        for line in md.read_text(encoding="utf-8").splitlines():
            low = line.strip().lower()
            if low.startswith("- bpm:"):
                try:
                    return float(line.split(":", 1)[1])
                except ValueError:
                    pass
    return 120.0


def analyze(ms_path: Path) -> dict:
    doc = ms_io.load(str(ms_path))
    bpm = _bpm_for(ms_path)
    meter = (4, 4)
    song = Song(doc, bpm=bpm, meter=meter)
    report = ms.report(song)
    score, _loss = to_s02(doc, time_base_us=int(round(60_000_000 / bpm)))
    payload = s02_api.build_payload(score)
    idx = s02_index.build(score)

    lines = s02_index._lines(score)  # noqa: SLF001 —— 内部工具
    motifs = []
    motif_note_ids = set()
    for m in idx.get("motifs") or []:
        occ = list(getattr(m, "occurrences", ()) or ())
        bars = [o[4] for o in occ if len(o) > 4]
        _line = lines.get(getattr(m, "line", None)) or []
        _pos = {n.id: i for i, n in enumerate(_line)}
        for o in occ:
            si, ei = _pos.get(o[0]), _pos.get(o[1])
            if si is not None and ei is not None and ei >= si:
                motif_note_ids.update(n.id for n in _line[si:ei + 1])
        motifs.append({
            "id": getattr(m, "id", ""),
            "length": getattr(m, "length", 0),
            "count": len(occ),
            "start_bar": min(bars) if bars else None,
            "end_bar": max(bars) if bars else None,
            "ivs": list(getattr(m, "ivs", ()) or ()),
        })

    variants = [{"motif": v[0], "kind": v[1], "start": v[2], "end": v[3],
                 "voice": v[4], "bar": v[5]} for v in (idx.get("variants") or [])]

    edges = idx.get("edges") or []
    by_kind: dict = {}
    for e in edges:
        if len(e) >= 4:
            by_kind[str(e[2])] = by_kind.get(str(e[2]), 0) + 1
    edge_rows = [{"a": e[0], "b": e[1], "kind": e[2], "weight": e[3]}
                 for e in edges if len(e) >= 4]

    q = report.get("quality") or {}
    metrics = dict(q.get("metrics") or {})
    dims = [{k: s.get("dims", {}).get(k) for k in ("tension", "drive", "space", "bright")}
            | {"id": s.get("id"), "start_bar": s.get("start_bar"),
               "end_bar": s.get("end_bar"), "label": s.get("label")}
            for s in (payload.get("sections") or [])]

    return {
        "song": ms_path.stem,
        "bpm": bpm,
        "summary": report.get("summary"),
        "quality": {"metrics": metrics,
                    "measurements": q.get("measurements"),
                    "coverage": q.get("coverage")},
        "motifs": motifs,
        "variants": variants,
        "motif_note_coverage": round(len(motif_note_ids) / max(1, len(score.notes)), 3),
        "edges_by_kind": by_kind,
        "sections": dims,
        "phrases": payload.get("phrases") or [],
        "harmony": payload.get("harmony") or {},
        "voice_endings": payload.get("voice_endings") or {},
        "edges": edge_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "inbox" / "omr_batch"))
    ap.add_argument("--out", default=str(ROOT / "inbox" / "s02"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.dir).glob("*/*.ms"))
    if not files:
        print("没有 .ms：", args.dir)
        return 1
    rows = []
    for f in files:
        try:
            data = analyze(f)
        except Exception as exc:  # noqa: BLE001
            print("失败:", f.name, type(exc).__name__, str(exc)[:120])
            continue
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in f.stem)[:60]
        (out / f"{safe}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        with (out / f"edges_{safe}.csv").open("w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=["a", "b", "kind", "weight"])
            wr.writeheader()
            wr.writerows(data["edges"])
        m = data["quality"]["metrics"] or {}
        rows.append({
            "song": data["song"], "notes": data["summary"]["notes"],
            "bpm": data["bpm"], "sections": len(data["sections"]),
            "phrases": len(data["phrases"]), "motifs": len(data["motifs"]),
            "variants": len(data["variants"]),
            "motif_cover": data["motif_note_coverage"],
            "tension": round(sum((s.get("tension") or 0) for s in data["sections"]) /
                             max(1, len(data["sections"])), 3),
            "density": round(sum((s.get("drive") or 0) for s in data["sections"]) /
                             max(1, len(data["sections"])), 3),
            "playability": m.get("playability"),
            "structure": m.get("structure"),
            "register": m.get("register"),
            "variety": m.get("variety"),
            "edges_next": data["edges_by_kind"].get("next", 0),
            "edges_similar": data["edges_by_kind"].get("similar", 0),
            "edges_variant": data["edges_by_kind"].get("variant", 0),
            "var_inv": sum(1 for v in data["variants"] if v["kind"] == "inversion"),
            "var_ret": sum(1 for v in data["variants"] if v["kind"] == "retrograde"),
            "var_rhy": sum(1 for v in data["variants"] if v["kind"] == "rhythmic"),
            "top_motif": max((x["count"] for x in data["motifs"]), default=0),
        })
        print(f"完成 {f.stem}: {data['summary']['notes']} 音, "
              f"{len(data['motifs'])} 动机, {len(data['variants'])} 变体")
    lines = ["# S02 结构/依附关系汇总（转换曲目）", "",
             "| 曲目 | 音 | 段 | 句 | 动机 | 变体 | 动机覆盖 | 张力均值 | 密度均值 | 可弹性 | 结构 | 音区 | 变化 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| {song} | {notes} | {sections} | {phrases} | {motifs} | {variants} | "
                     "{motif_cover} | {tension} | {density} | {playability} | {structure} | "
                     "{register} | {variety} |".format(**r))
    lines += ["", "## 关系数据（依附/重复/变体）", "",
              "| 曲目 | next 边 | similar 边 | variant 边 | 倒影 | 逆行 | 节奏变形 | 单动机最多出现 |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| {song} | {edges_next} | {edges_similar} | {edges_variant} | "
                     "{var_inv} | {var_ret} | {var_rhy} | {top_motif} |".format(**r))
    lines += ["", "数据文件：`inbox/s02/<曲名>.json`；关系边：`edges_<曲名>.csv`。"]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("汇总：", out / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
