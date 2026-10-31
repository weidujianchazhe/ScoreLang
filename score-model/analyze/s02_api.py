# -*- coding: utf-8 -*-
"""S02 分析数据接口：把分析结果组装成一份 JSON 视图。"""
from __future__ import annotations

from pathlib import Path

import s02_index
import s02_io
import s02_probe
import s02_score
import s02_segment
import s02_weights as wt


def payload(s02_path, *, s02x_path=None, weights=None, with_notes: bool = False) -> dict:
    """读文件并组装前端视图（不抛：读失败会给出 error 字段）。"""
    try:
        score = s02_io.parse(Path(s02_path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"读入 .s02 失败：{e}"}
    idx_con = None
    idx_path = s02x_path or str(Path(s02_path).with_suffix(".s02x"))
    if Path(idx_path).exists():
        idx_con = s02_index.open_index(idx_path)
    try:
        return build_payload(score, index_con=idx_con, weights=weights,
                             with_notes=with_notes)
    finally:
        if idx_con is not None:
            idx_con.close()


def _windows_with_raw(score, dim_windows: list) -> list:
    """把 dims 窗口与 probe/harmony/fingering/perturb 的原始量合并（结构化质量要用）。"""
    import s02_fingering
    import s02_perturb
    try:
        fg = {w["window"]: w for w in s02_fingering.analyze(score)["windows"]}
    except Exception:
        fg = {}
    try:
        pb = {w["window"]: w for w in s02_perturb.analyze(score)["windows"]}
    except Exception:
        pb = {}
    out = []
    for w in dim_windows:
        row = {k: v for k, v in w.items() if k != "raw"}
        n = int(row.get("window") or 0)
        g, q = fg.get(n, {}), pb.get(n, {})
        row["density"] = g.get("notes")
        row["centroid"] = None
        row["hard"] = g.get("hard", 0.0)
        row["perturb"] = q.get("count", 0)
        out.append(row)
    # probe 补密度/音区（窗口号一致）
    try:
        import s02_probe
        pr = {b["window"]: b for b in s02_probe.analyze(score)["bars"]}
        for row in out:
            b = pr.get(int(row["window"]), {})
            if b.get("density") is not None:
                row["density"] = b.get("density")
            if b.get("centroid") is not None:
                row["centroid"] = b.get("centroid")
    except Exception:
        pass
    return out


def _inst_field(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _voice_endings(score) -> dict:
    """每个乐器实例的最后音：结束位置 / 末音力度 / 释放状态（用于收尾评估）。"""
    types = {}
    for ins in getattr(score, "instruments", []) or []:
        try:
            key = str(_inst_field(ins, "id"))
            if key.startswith("P") and key[1:].isdigit():
                key = key[1:]
            types[key] = _inst_field(ins, "type")
        except Exception:
            pass
    by = {}
    for n in getattr(score, "notes", []):
        iid = int(getattr(n, "instrument_id", 1) or 1)
        end = int(getattr(n, "onset", 0)) + int(getattr(n, "duration", 0))
        d = by.get(iid)
        if d is None or end >= d["last_end"]:
            by[iid] = {
                "inst": iid,
                "last_end": end,
                "last_permille": getattr(n, "dynamics_permille", None),
                "release_state": getattr(n, "release_state", "given"),
                "type": types.get(str(getattr(n, "instrument_id", 1))),
            }
    perms_all = [int(getattr(n, "dynamics_permille"))
                 for n in getattr(score, "notes", [])
                 if getattr(n, "dynamics_permille", None) is not None]
    avg_pm = (sum(perms_all) / len(perms_all)) if perms_all else None
    if not by:
        return {"instances": [], "piece_end": 0, "avg_permille": avg_pm}
    ends = [d["last_end"] for d in by.values()]
    piece_end = max(ends) or 1
    return {
        "instances": [by[k] for k in sorted(by)],
        "piece_end": piece_end,
        "stagger": (max(ends) - min(ends)) / piece_end,
        "avg_permille": avg_pm,
    }


def _technique_stats(score) -> dict:
    """技术密度统计（测量值，与好坏无关）。"""
    notes = list(getattr(score, "notes", []) or [])
    acts = list(getattr(score, "actions", []) or [])
    arts = list(getattr(score, "articulations", []) or [])
    n = len(notes)
    bars = 1
    for x in notes:
        try:
            bars = max(bars, int(getattr(x, "measure", 0)) + 1)
        except Exception:
            pass
    tech = len(acts) + len(arts)
    return {"notes": n, "bars": bars, "actions": len(acts),
            "articulations": len(arts),
            "per_note": round(tech / n, 4) if n else None,
            "per_bar": round(tech / bars, 4) if bars else None}


def build_payload(score, *, index_con=None, weights=None, with_notes: bool = False) -> dict:
    """从内存里的 ScoreV02 组装视图（报告/flow 复用，避免重复解析与重复建索引）。"""
    import s02_harmony

    cfg = weights if isinstance(weights, dict) else wt.load(weights)
    seg = s02_segment.segment(score, weights=cfg)
    sc = s02_score.analyze_sections(score, seg["sections"], weights=cfg)
    pr = s02_probe.analyze(score)
    dims = {x["id"]: x for x in sc["sections"]}

    sections = []
    for x in seg["sections"]:
        d = dims.get(x["id"], {})
        sections.append({
            "id": x["id"], "start_bar": x["start_bar"], "end_bar": x["end_bar"],
            "label": x["label"], "why": x["why"], "notes": x["notes"],
            "perturb": x.get("perturb", 0), "tension_adj": x.get("tension_adj"),
            "features": x["features"], "repeat": x["repeat"],
            "dims": {k: d.get(k) for k in s02_score.DIMS},
        })

    out = {
        "summary": pr["summary"],
        "sections": sections,
        "phrases": seg["phrases"],
        "perturbations": {
            "events": seg.get("perturb", {}).get("events", []),
            "overall": seg.get("perturb", {}).get("overall", {}),
        },
        "windows": _windows_with_raw(score, sc["windows"]),
        "spark": pr["spark"],
        "harmony": s02_harmony.analyze(score).get("overall", {}),
        "voice_endings": _voice_endings(score),
        "constraint_mode": getattr(score, "constraint_mode", None),
        "technique": _technique_stats(score),
    }

    if index_con is not None:
        con = index_con
        try:
            out["motifs"] = [{"id": r[0], "signature": r[1], "length": r[2],
                              "count": r[3], "variants": r[4]}
                             for r in s02_index.motifs(con)]
            out["variants"] = [{"motif": r[0], "transform": r[1], "start": r[2],
                                "end": r[3], "voice": r[4], "bar": r[5]}
                               for r in s02_index.variants(con)]
            out["stats"] = s02_index.stats(con)
        except Exception:
            out["motifs"] = out.get("motifs", [])
        # 注意：连接由调用方负责关闭（payload() 会关，build_payload 不关）
    else:
        out["motifs"] = []
        out["variants"] = []
        out["stats"] = {}

    try:
        import s02_quality
        out["quality"] = s02_quality.analyze(out, weights=cfg)
    except Exception as e:  # noqa: BLE001
        out["quality"] = {"error": str(e)}

    if with_notes:
        out["notes"] = [{"id": n.id, "onset": n.onset, "duration": n.duration,
                         "voice": n.voice, "staff": n.staff, "measure": n.measure,
                         "semi": n.pitch.semitone,
                         "permille": n.dynamics_permille,
                         "release": getattr(n, "release_state", "given"),
                         "inst": getattr(n, "instrument_id", 1)}
                        for n in score.notes]
    return out
