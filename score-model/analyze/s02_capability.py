# -*- coding: utf-8 -*-
"""S02 演奏能力覆盖：工具知道"能用什么"，也知道"该怎么用"。"""
from __future__ import annotations

import ms_instruments as reg

# 每个机制最值得用的转折（按"听感收益"排序，经验值；只用于提示排序，不参与评分）
_TURN_PRIORITY = (
    "bow_change", "pizz", "arco", "harmonic", "col_legno", "tremolo",
    "mute_on", "mute_off", "retrigger", "breath", "restrike", "mallet",
    "roll", "brush", "rim_shot", "flutter", "growl", "half_valve",
    "key_noise", "key_click", "inhale", "mute_cup", "mute_harmon",
    "mute_plunger", "mallet_soft", "mallet_hard", "bow_up", "bow_down",
)

_PEDAL_PRIORITY = ("sustain", "sostenuto", "una_corda", "sordino", "hihat")
_CURVE_PRIORITY = ("dynamics", "brightness", "pitch_cents", "vibrato", "bow_position")

# 写法示例（写谱 API）
_HOW = {
    "turn": "au.write_turn(event_id=<音 id>, kind='{kind}')  # 转折挂在音头",
    "pedal": "au.write_pedal(piano_id={iid}, kind='{kind}', start_us=…, end_us=…, permille=1000)",
    "curve": ("# 曲线用 ev.CurvePoint(instrument_id={iid}, param='{param}', "
              "time_us=…, value=…, ramp=1) 加进 to_document(curves=[...])"),
    "articulation": "au.write_note(..., articulation='{kind}')（写时折进时值/力度）",
    "ornament": "au.write_note(..., ornament='{kind}')（装饰音会展开成多个音）",
    "instrument": "au.make_instrument('P{n}', '{type}')",
}


def _turns_for(mech: str) -> list:
    out = []
    for kind, mechs in reg.ACTION_MECHS.items():
        if mechs is None or mech in mechs:
            out.append(kind)
    return sorted(out, key=lambda k: (_TURN_PRIORITY.index(k)
                                      if k in _TURN_PRIORITY else 99, k))


def available_instruments(*, family: str | None = None) -> list:
    """可用乐器清单（外部 AI 最常问"我有哪些乐器"）。"""
    out = []
    for code in sorted(reg._BY_CODE):
        try:
            spec = reg.resolve(code)
        except Exception:
            continue
        if family and spec.get("family") != family:
            continue
        out.append({
            "type": code, "family": spec.get("family"), "mechanism": spec.get("mechanism"),
            "range": spec.get("range"), "poly": spec.get("poly"),
            "pedals": list(spec.get("pedals") or ()),
        })
    return out


def analyze(doc) -> dict:
    """MS 乐谱模型 → 能力覆盖报告。"""
    # 音符 id → 乐器，用于把 turns 归到乐器上
    inst_of_event = {e.id: e.instrument_id for e in doc.events}

    per_inst = []
    for inst in getattr(doc, "instruments", []) or []:
        try:
            iid = int(str(inst.id).lstrip("Pp"))
        except Exception:
            iid = None
        try:
            spec = reg.resolve(inst.type, inst.subtype)
        except KeyError:
            per_inst.append({"id": inst.id, "type": inst.type, "error": "未登记乐器类型"})
            continue
        mech = spec.get("mechanism")
        avail_turns = _turns_for(mech)
        avail_pedals = list(spec.get("pedals") or ())
        avail_curves = list(_CURVE_PRIORITY)
        avail_arts = list(reg.ARTICULATIONS_BY_MECH.get(mech, ()))
        avail_orns = list(reg.ORNAMENTS_BY_MECH.get(mech, ()))

        used_turns, used_pedals, used_curves = {}, set(), set()
        for t in getattr(doc, "turns", []) or []:
            if inst_of_event.get(t.event_id) == iid:
                used_turns[t.kind] = used_turns.get(t.kind, 0) + 1
        for p in getattr(doc, "pedals", []) or []:
            if getattr(p, "instrument_id", None) == iid:
                used_pedals.add(p.kind)
        for c in getattr(doc, "curves", []) or []:
            if getattr(c, "instrument_id", None) == iid:
                used_curves.add(c.param)

        unused_turns = [k for k in avail_turns if k not in used_turns]
        unused_pedals = [k for k in avail_pedals if k not in used_pedals]
        unused_curves = [k for k in avail_curves if k not in used_curves]

        hints = []
        for k in unused_turns[:4]:
            hints.append({"kind": "turn", "name": k,
                          "how": _HOW["turn"].format(kind=k)})
        for k in unused_pedals[:3]:
            hints.append({"kind": "pedal", "name": k,
                          "how": _HOW["pedal"].format(iid=iid or 1, kind=k)})
        for k in unused_curves[:3]:
            hints.append({"kind": "curve", "name": k,
                          "how": _HOW["curve"].format(iid=iid or 1, param=k)})
        for k in avail_arts[:2]:
            hints.append({"kind": "articulation", "name": k,
                          "how": _HOW["articulation"].format(kind=k)})
        for k in avail_orns[:2]:
            hints.append({"kind": "ornament", "name": k,
                          "how": _HOW["ornament"].format(kind=k)})

        per_inst.append({
            "id": inst.id, "type": inst.type, "family": spec.get("family"),
            "mechanism": mech, "range": spec.get("range"), "poly": spec.get("poly"),
            "available": {"turns": avail_turns, "pedals": avail_pedals,
                          "curves": avail_curves, "articulations": avail_arts,
                          "ornaments": avail_orns},
            "used": {"turns": used_turns, "pedals": sorted(used_pedals),
                     "curves": sorted(used_curves)},
            "unused": {"turns": unused_turns, "pedals": unused_pedals,
                       "curves": unused_curves},
            "hints": hints,
        })

    # 全局：机制多样性 + 表情层
    mechs = sorted({x.get("mechanism") for x in per_inst if x.get("mechanism")})
    n_turns = len(getattr(doc, "turns", []) or [])
    n_pedals = len(getattr(doc, "pedals", []) or [])
    n_curves = len(getattr(doc, "curves", []) or [])
    gaps = []
    if len(per_inst) == 1:
        gaps.append("只用了 1 件乐器——没有音色/音区对比")
    if len(mechs) == 1:
        gaps.append(f"只用了 1 种发声机制（{mechs[0]}）——编制维度单一")
    if n_turns == 0:
        gaps.append("没有任何演奏转折（换弓/拨弦/闷音/滚奏…）——所有音头都是默认的")
    if n_pedals == 0 and any("sustain" in (x.get("available", {}).get("pedals") or [])
                             for x in per_inst):
        gaps.append("有可踩踏板的乐器但整曲没用踏板")
    if n_curves == 0:
        gaps.append("没有任何连续曲线（dynamics/brightness/pitch_cents/vibrato）——力度只是阶跃")

    return {
        "instruments": per_inst,
        "summary": {
            "instrument_count": len(per_inst),
            "mechanisms": mechs,
            "mechanism_count": len(mechs),
            "turns": n_turns, "pedals": n_pedals, "curves": n_curves,
            "gaps": gaps,
        },
        "note": "这是能力覆盖，不是质量分；奏法/装饰音在 MS 里不单独存，只能给可用清单与写法。",
    }
