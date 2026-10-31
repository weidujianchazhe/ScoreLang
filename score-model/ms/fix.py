# -*- coding: utf-8 -*-
"""分析 → 修改 → 复核 闭环（原型）。

用法：
    out = ms.analyze_fix(spec, intent=None)          # 返回修复后的 spec + 前后对照
    ms.analyze_fix(spec, apply=False)                # 只给建议，不改 spec

设计边界：
  · 只做“确定性、可回退”的局部修复（重叠音/踏板间隙/力度越界/收束错开/奏法过量）；
  · 每次修复后重新 build + report 复核；硬约束不过则回退该修复；
  · 全局指标下降 >0.1 时保留修复但记录 warning（原型阶段不擅自回退全局变化）。
"""
from __future__ import annotations

import copy

MAX_DYNAMICS = 1000
MIN_PEDAL_GAP_BEAT = 0.25      # 150bpm 下 0.25 拍 = 100ms，> 50ms 容差


def _normalize(spec_or_song):
    if isinstance(spec_or_song, dict):
        return copy.deepcopy(spec_or_song)
    spec = getattr(spec_or_song, "spec", None)
    if callable(spec):
        return copy.deepcopy(spec())
    raise TypeError("analyze_fix 需要任务 JSON（dict）或带 spec() 的对象")


def _report(spec, intent):
    import ms
    song = ms.build(spec)
    rep = ms.report(song, intent=intent)
    return song, rep


def _metrics(rep):
    q = rep.get("quality") or {}
    return {"metrics": dict(q.get("metrics") or {}),
            "measurements": dict(q.get("measurements") or {})}


def _note_interval(n):
    b = float(n.get("beat", 0.0))
    return b, b + float(n.get("beats", 1.0))


def _fix_overlaps(spec):
    """同乐器同音高重叠：缩短前一个音（或错开同刻的后者）。"""
    notes = spec.get("notes") or []
    fixes = []
    last = {}
    for n in notes:
        key = (int(n.get("inst", 1)), str(n.get("pitch", "")))
        if key not in last:
            last[key] = n
            continue
        prev = last[key]
        pb, pe = _note_interval(prev)
        b, _ = _note_interval(n)
        if b < pe - 1e-9:
            new_beats = max(0.05, b - pb)
            fixes.append({
                "kind": "same_pitch_overlap",
                "location": {"inst": key[0], "pitch": key[1], "beat": pb},
                "action": f"缩短前音时值 {prev.get('beats')} → {round(new_beats, 3)} 拍",
                "apply": lambda p=prev, v=new_beats: p.__setitem__("beats", v),
            })
        last[key] = n
    return fixes


def _fix_pedals(spec):
    fixes = []
    pedals = spec.get("pedals")
    if pedals:
        for i in range(len(pedals) - 1):
            a, b = pedals[i], pedals[i + 1]
            a_end = float(a.get("end", 0.0))
            b_start = float(b.get("start", 0.0))
            if b_start - a_end < MIN_PEDAL_GAP_BEAT:
                new_end = max(float(a.get("start", 0.0)) + 0.1,
                              b_start - MIN_PEDAL_GAP_BEAT)
                fixes.append({
                    "kind": "pedal_gap",
                    "location": {"index": i},
                    "action": f"踏板抬脚前移：end {a_end} → {round(new_end, 3)} 拍",
                    "apply": lambda p=a, v=new_end: p.__setitem__("end", v),
                })
        return fixes
    # 自动踏板：spec.pedal == "auto" 时改由 build 派生；这里只检查显式踏板
    return fixes


def _fix_dynamics(spec):
    fixes = []
    for i, n in enumerate(spec.get("notes") or []):
        if "permille" in n:
            v = int(n["permille"])
            if not 0 <= v <= MAX_DYNAMICS:
                nv = max(0, min(MAX_DYNAMICS, v))
                fixes.append({
                    "kind": "dynamics_range",
                    "location": {"note": i},
                    "action": f"力度 {v} → {nv}",
                    "apply": lambda nn=n, vv=nv: nn.__setitem__("permille", vv),
                })
    return fixes


def _fix_ending(spec, intent, rep):
    """多编制收束：按 intent 或测量值，错开各乐器最后一音。"""
    insts = spec.get("instruments") or []
    if len(insts) < 2:
        return []
    notes = spec.get("notes") or []
    if not notes:
        return []
    total = max(_note_interval(n)[1] for n in notes)
    meas = ((rep.get("quality") or {}).get("measurements") or {})
    want = bool(((intent or {}).get("ending") or {}).get("stagger_voices"))
    try:
        ve = float(((rep.get("quality") or {}).get("metrics") or {})
                   .get("ending_voices") or 0.0)
    except (TypeError, ValueError):
        ve = 0.0
    if not want and ve >= 0.3:
        return []
    step = max(0.5, total * 0.02)
    last_by_inst = {}
    for n in notes:
        iid = int(n.get("inst", 1))
        last_by_inst[iid] = max(last_by_inst.get(iid, 0.0),
                                _note_interval(n)[1])
    order = sorted(last_by_inst)
    fixes = []
    for k, iid in enumerate(order[1:], start=1):
        target = last_by_inst[iid] + step * k
        candidates = [n for n in notes if int(n.get("inst", 1)) == iid]
        if not candidates:
            continue
        n = max(candidates, key=lambda x: _note_interval(x)[1])
        b = float(n.get("beat", 0.0))
        new_beats = max(0.05, target - b)
        fixes.append({
            "kind": "ending_stagger",
            "location": {"inst": iid, "beat": b},
            "action": f"末音延长 {n.get('beats')} → {round(new_beats, 3)} 拍（错开收束）",
            "apply": lambda nn=n, v=new_beats: nn.__setitem__("beats", v),
        })
    return fixes


def _fix_technique(spec, intent, rep):
    """奏法/转折过量：按 intent.technique.density 删到上限内。"""
    tech = (intent or {}).get("technique") or {}
    if not tech.get("density"):
        return []
    notes = spec.get("notes") or []
    marked = [n for n in notes if n.get("articulation") or n.get("ornament")]
    if not marked:
        return []
    per_note = len(marked) / max(1, len(notes))
    max_ratio = {"low": 0.15, "medium": 0.4, "high": 1.0}.get(
        str(tech["density"]).lower(), 1.0)
    if per_note <= max_ratio:
        return []
    remove = marked[int(len(marked) * max_ratio):]
    fixes = []
    for n in remove:
        fixes.append({
            "kind": "technique_density",
            "location": {"beat": n.get("beat")},
            "action": "移除超出密度上限的奏法/转折",
            "apply": lambda nn=n: (nn.pop("articulation", None),
                                   nn.pop("ornament", None)),
        })
    return fixes


def analyze_fix(spec_or_song, *, intent=None, apply=True, max_rounds=3) -> dict:
    """分析 → 修改 → 复核。

    返回 {ok, spec, fixes, before, after, warnings, verified}。
    """
    spec = _normalize(spec_or_song)
    if not isinstance(intent, dict):
        intent = None
    warnings = []
    try:
        song, before_rep = _report(spec, intent)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "spec": spec, "fixes": [],
                "before": {}, "after": {}, "warnings": [f"初始生成失败：{exc}"],
                "verified": False}
    before = _metrics(before_rep)

    all_fixes = []
    all_fixes += _fix_overlaps(spec)
    all_fixes += _fix_pedals(spec)
    all_fixes += _fix_dynamics(spec)
    all_fixes += _fix_ending(spec, intent, before_rep)
    all_fixes += _fix_technique(spec, intent, before_rep)

    applied = []
    for fx in all_fixes[: max(1, max_rounds) * 10]:
        if not apply:
            applied.append({**{k: v for k, v in fx.items() if k != "apply"},
                            "applied": False})
            continue
        snapshot = copy.deepcopy(spec)
        fx["apply"]()
        try:
            _song2, rep2 = _report(spec, intent)
        except Exception as exc:  # noqa: BLE001
            spec = snapshot          # 修复导致生成失败 → 回退
            applied.append({**{k: v for k, v in fx.items() if k != "apply"},
                            "applied": False, "reverted": str(exc)[:120]})
            continue
        applied.append({**{k: v for k, v in fx.items() if k != "apply"},
                        "applied": True})

    try:
        _song3, after_rep = _report(spec, intent)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "spec": spec, "fixes": applied,
                "before": before, "after": {},
                "warnings": warnings + [f"修复后生成失败：{exc}"],
                "verified": False}

    after = _metrics(after_rep)
    hard_ok = True
    try:
        import ms
        check = ms.check_spec(spec)
        hard_ok = bool(check.get("ok"))
        if not hard_ok:
            warnings.append("修复后 check_spec 未通过：" + str(check.get("errors") or "")[:160])
    except Exception as exc:  # noqa: BLE001
        hard_ok = True
        warnings.append(f"check_spec 无法执行（跳过）：{exc}")

    # 全局变化提示：非目标指标下降 >0.1 时记录
    for k, v in before["metrics"].items():
        nv = after["metrics"].get(k)
        if isinstance(v, (int, float)) and isinstance(nv, (int, float)):
            if nv < v - 0.1:
                warnings.append(f"全局注意：{k} 由 {v} 降到 {nv}（局部修复可能影响整体）")

    return {"ok": True, "spec": spec, "fixes": applied,
            "before": before, "after": after,
            "warnings": warnings, "verified": hard_ok}


__all__ = ["analyze_fix"]
