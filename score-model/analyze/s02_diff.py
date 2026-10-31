# -*- coding: utf-8 -*-
"""S02 改前改后对比（P8-1）：把"我改了哪里、结果变了多少"说清楚。

三层对比：
  1. **音符级**：按 id 对齐，列出新增/删除/修改（音高/起始/时值/力度/声部）；
  2. **结构级**：段落按小节重叠配对，比标签、紧张度、四个维度；
  3. **窗口级**：密度/音区/难度/扰动 变化最大的小节。

用法（CLI）：
    mscli s02 diff old.s02 new.s02 -o diff.md
    mscli s02 diff old.ms new.ms --time-base 500000
"""
from __future__ import annotations

import s02_fingering
import s02_probe
import s02_perturb
import s02_score
import s02_segment

NOTE_FIELDS = ("semi", "onset", "duration", "permille", "voice")


def _note_map(score) -> dict:
    return {n.id: n for n in score.notes}


def _field(n, name):
    if name == "semi":
        return n.pitch.semitone
    if name == "permille":
        return n.dynamics_permille
    return getattr(n, name, None)


def note_changes(a, b) -> dict:
    """音符级差异：{added, removed, changed}；changed 里带字段级 old/new。"""
    ma, mb = _note_map(a), _note_map(b)
    added = [mb[i] for i in mb if i not in ma]
    removed = [ma[i] for i in ma if i not in mb]
    changed = []
    for i in ma:
        if i not in mb:
            continue
        fields = {}
        for f in NOTE_FIELDS:
            va, vb = _field(ma[i], f), _field(mb[i], f)
            if va != vb:
                fields[f] = {"old": va, "new": vb}
        if fields:
            changed.append({"id": i, "fields": fields})
    return {"added": added, "removed": removed, "changed": changed}


def _windows(score) -> dict:
    """逐窗口的对比用指标：密度/音区/难度/扰动数。"""
    pr = s02_probe.analyze(score)
    fg = s02_fingering.analyze(score)
    pb = s02_perturb.analyze(score)
    hard = {w["window"]: w["hard"] for w in fg["windows"]}
    pert = {w["window"]: w["count"] for w in pb["windows"]}
    out = {}
    for b in pr["bars"]:
        w = b["window"]
        out[w] = {
            "density": b.get("density"),
            "centroid": b.get("centroid"),
            "hard": hard.get(w, 0.0),
            "perturb": pert.get(w, 0),
        }
    return out


def _sections(score) -> list:
    seg = s02_segment.segment(score)
    sc = s02_score.analyze_sections(score, seg["sections"])
    dims = {x["id"]: x for x in sc["sections"]}
    out = []
    for x in seg["sections"]:
        d = dims.get(x["id"], {})
        out.append({
            "id": x["id"], "start_bar": x["start_bar"], "end_bar": x["end_bar"],
            "label": x["label"], "tension": x.get("tension_adj"),
            "perturb": x.get("perturb", 0),
            "dims": {k: d.get(k) for k in s02_score.DIMS},
        })
    return out


def _pair_sections(sec_a: list, sec_b: list) -> list:
    """按小节重叠面积把两版的段落配对（一对一，贪心）。"""
    cand = []
    for i, x in enumerate(sec_a):
        for j, y in enumerate(sec_b):
            overlap = min(x["end_bar"], y["end_bar"]) - max(x["start_bar"], y["start_bar"]) + 1
            if overlap > 0:
                cand.append((overlap, i, j))
    cand.sort(reverse=True)
    used_a, used_b, pairs = set(), set(), []
    for _ov, i, j in cand:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((sec_a[i], sec_b[j]))
    for i, x in enumerate(sec_a):
        if i not in used_a:
            pairs.append((x, None))
    for j, y in enumerate(sec_b):
        if j not in used_b:
            pairs.append((None, y))
    return sorted(pairs, key=lambda p: (p[0] or p[1])["start_bar"])


def compare(score_a, score_b, *, top: int = 10) -> dict:
    """完整对比结果（可直接 json 化）。"""
    nc = note_changes(score_a, score_b)
    wa, wb = _windows(score_a), _windows(score_b)
    movers = []
    for w in sorted(set(wa) | set(wb)):
        a, b = wa.get(w, {}), wb.get(w, {})
        row = {}
        for f in ("density", "centroid", "hard", "perturb"):
            va, vb = a.get(f), b.get(f)
            if va is None or vb is None:
                continue
            if abs((vb or 0) - (va or 0)) > 1e-9:
                row[f] = {"old": va, "new": vb, "delta": round((vb or 0) - (va or 0), 3)}
        if row:
            movers.append({"window": w, **row})
    movers.sort(key=lambda r: -max(abs(v["delta"]) for v in
                                   (r[k] for k in r if k != "window")))
    secs_a, secs_b = _sections(score_a), _sections(score_b)
    pairs = []
    for x, y in _pair_sections(secs_a, secs_b):
        row = {"a": x["id"] if x else None, "b": y["id"] if y else None,
               "bars_a": f"{x['start_bar']}–{x['end_bar']}" if x else None,
               "bars_b": f"{y['start_bar']}–{y['end_bar']}" if y else None,
               "label_a": x["label"] if x else None,
               "label_b": y["label"] if y else None,
               "changed": (x is None or y is None or x["label"] != y["label"]
                           or abs((x.get("tension") or 0) - (y.get("tension") or 0)) > 1e-6)}
        if x and y:
            row["tension"] = {"old": x.get("tension"), "new": y.get("tension")}
            row["dims"] = {k: {"old": x["dims"].get(k), "new": y["dims"].get(k)}
                           for k in s02_score.DIMS
                           if abs((x["dims"].get(k) or 0) - (y["dims"].get(k) or 0)) > 1e-6}
        pairs.append(row)
    return {
        "notes": {"added": len(nc["added"]), "removed": len(nc["removed"]),
                  "changed": len(nc["changed"]), "detail": nc},
        "windows": {"count": len(set(wa) | set(wb)), "movers": movers[:top]},
        "sections": {"before": len(secs_a), "after": len(secs_b), "pairs": pairs},
    }


def to_markdown(diff: dict, *, title: str = "") -> str:
    n = diff["notes"]
    lines = [f"# S02 改动对比{f' · {title}' if title else ''}", "",
             "## 0. 概览", "",
             f"- 音符：新增 **{n['added']}** · 删除 **{n['removed']}** · 修改 **{n['changed']}**",
             f"- 段落：{diff['sections']['before']} 段 → {diff['sections']['after']} 段",
             f"- 有变化的窗口：{len(diff['windows']['movers'])} 个（列出前 {len(diff['windows']['movers'])}）", ""]

    lines += ["## 1. 音符级改动", ""]
    if not (n["added"] or n["removed"] or n["changed"]):
        lines += ["（没有音符级改动）", ""]
    else:
        lines += ["| 类型 | id | 变化 |", "|---|---|---|"]
        for e in n["detail"]["changed"][:20]:
            desc = "；".join(f"{k} {v['old']} → {v['new']}" for k, v in e["fields"].items())
            lines.append(f"| 修改 | {e['id']} | {desc} |")
        for e in n["detail"]["added"][:10]:
            lines.append(f"| 新增 | {e.id} | 音高 {e.pitch.semitone} · 第 {e.measure + 1} 小节 |")
        for e in n["detail"]["removed"][:10]:
            lines.append(f"| 删除 | {e.id} | 音高 {e.pitch.semitone} · 第 {e.measure + 1} 小节 |")
        lines.append("")

    lines += ["## 2. 结构级变化", "",
              "| 旧段 | 新段 | 小节（旧→新） | 标签（旧→新） | 紧张度 | 维度变化 |",
              "|---|---|---|---|---|---|"]
    for p in diff["sections"]["pairs"]:
        dims = ""
        if p.get("dims"):
            dims = "；".join(f"{k} {v['old']:.2f}→{v['new']:.2f}" for k, v in p["dims"].items())
        tension = ""
        if p.get("tension"):
            tension = f"{p['tension']['old']}→{p['tension']['new']}"
        lines.append(f"| {p['a'] or '—'} | {p['b'] or '—'} | {p['bars_a'] or '—'} → "
                     f"{p['bars_b'] or '—'} | {p['label_a'] or '—'} → {p['label_b'] or '—'} | "
                     f"{tension} | {dims or '—'} |")
    lines.append("")

    lines += ["## 3. 窗口级最大变化", "",
              "| 小节 | 密度 | 音区 | 难度 | 扰动数 |", "|---|---|---|---|---|"]
    for m in diff["windows"]["movers"]:
        def cell(f):
            if f not in m:
                return "—"
            return f"{m[f]['old']} → {m[f]['new']}（{m[f]['delta']:+.2f}）"
        lines.append(f"| {m['window']} | {cell('density')} | {cell('centroid')} | "
                     f"{cell('hard')} | {cell('perturb')} |")
    if not diff["windows"]["movers"]:
        lines += ["（窗口级没有变化）"]
    lines.append("")

    # 结论式提示
    notes = []
    changed_labels = [p for p in diff["sections"]["pairs"] if p["a"] and p["b"]
                      and p["label_a"] != p["label_b"]]
    if changed_labels:
        notes.append("标签变了的段：" + "、".join(
            f"{p['a']}→{p['b']}（{p['label_a']}→{p['label_b']}）" for p in changed_labels))
    harder = [m for m in diff["windows"]["movers"] if "hard" in m and m["hard"]["delta"] > 0.05]
    easier = [m for m in diff["windows"]["movers"] if "hard" in m and m["hard"]["delta"] < -0.05]
    if harder:
        notes.append("变难的小节：" + "、".join(str(m["window"]) for m in harder[:8]))
    if easier:
        notes.append("变简单的小节：" + "、".join(str(m["window"]) for m in easier[:8]))
    denser = [m for m in diff["windows"]["movers"]
              if "density" in m and (m["density"]["delta"] or 0) > 0.5]
    if denser:
        notes.append("变密的小节：" + "、".join(str(m["window"]) for m in denser[:8]))
    if notes:
        lines += ["## 4. 提示", ""] + [f"- {x}" for x in notes] + [""]
    return "\n".join(lines) + "\n"
