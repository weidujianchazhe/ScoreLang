# -*- coding: utf-8 -*-
"""诊断增强：把问题定位到“小节/拍/乐器/音”，并给 AI 修改方向。

只诊断，不改音符：
    res = ms.diagnose(spec, intent=None)
    for f in res["findings"]:
        print(f["where"], f["why"], f["suggestion"])

设计边界：
  · 不自动移调/改节奏/重排声部（这些属于 AI 判断）；
  · 每条 finding 带位置、原因、建议、严重度；建议只描述方向。
"""
from __future__ import annotations

import copy


def _spec_of(spec_or_song):
    if isinstance(spec_or_song, dict):
        return copy.deepcopy(spec_or_song)
    sp = getattr(spec_or_song, "_spec", None)
    if isinstance(sp, dict):
        return copy.deepcopy(sp)
    sp = getattr(spec_or_song, "spec", None)
    if callable(sp):
        return copy.deepcopy(sp())
    raise TypeError("diagnose 需要任务 JSON（dict）或 Song")


def _where(spec, beat, *, inst=None, note=None):
    meter = tuple(spec.get("meter") or (4, 4))
    bpb = max(1, int(meter[0]))
    try:
        b = float(beat)
    except (TypeError, ValueError):
        b = 0.0
    out = {"bar": int(b // bpb) + 1, "beat": round(b % bpb, 3)}
    if inst is not None:
        out["inst"] = int(inst)
    if note is not None:
        out["note"] = int(note)
    return out


def _finding(code, severity, where, why, suggestion, verify=None):
    return {"code": code, "severity": severity, "where": where,
            "why": why, "suggestion": suggestion,
            "verify": verify or f"改后重跑 `mscli ms diagnose task.json`，不再出现 {code}"}


def _overlaps(spec):
    out = []
    last = {}
    for i, n in enumerate(spec.get("notes") or []):
        key = (int(n.get("inst", 1)), str(n.get("pitch", "")))
        b = float(n.get("beat", 0.0))
        e = b + float(n.get("beats", 1.0))
        if key in last:
            pi, pb, pe = last[key]
            if b < pe - 1e-9:
                out.append(_finding(
                    "same_pitch_overlap", "high",
                    _where(spec, pb, inst=key[0], note=pi),
                    f"乐器 {key[0]} 的 {key[1]} 与前一个音重叠"
                    f"（前音 {round(pb, 3)}–{round(pe, 3)}，后音从 {round(b, 3)} 开始）",
                    "缩短前音时值，或把后音错开（由 AI 决定音乐上是否保留）",
                    f"改后重跑 `mscli ms diagnose task.json`：不再出现 same_pitch_overlap"))
        last[key] = (i, b, e)
    return out


def _pedal_gaps(spec):
    out = []
    ps = spec.get("pedals") or []
    for i in range(len(ps) - 1):
        a, b = ps[i], ps[i + 1]
        gap = float(b.get("start", 0)) - float(a.get("end", 0))
        if gap < 0.25:
            out.append(_finding(
                "pedal_gap", "high", _where(spec, a.get("end", 0), inst=a.get("inst", 1)),
                f"踏板 {i} 与 {i + 1} 间隙只有 {round(gap, 3)} 拍（< 0.25，150bpm 下不足 100ms）",
                "抬脚提前或缩短踏板，留 ≥0.25 拍间隙（否则会被合并成长踏板）",
                "改后重跑 `mscli ms diagnose task.json`：不再出现 pedal_gap"))
    return out


def _ending(spec, report):
    out = []
    notes = spec.get("notes") or []
    insts = spec.get("instruments") or []
    if len(insts) < 2 or not notes:
        return out
    q = (report.get("quality") or {}).get("metrics") or {}
    ve = q.get("ending_voices")
    if not isinstance(ve, (int, float)) or ve >= 0.35:
        return out
    last = {}
    for n in notes:
        iid = int(n.get("inst", 1))
        e = float(n.get("beat", 0)) + float(n.get("beats", 1))
        last[iid] = max(last.get(iid, 0.0), e)
    if len(last) < 2:
        return out
    order = sorted(last.items(), key=lambda kv: kv[1])
    piece_end = max(last.values())
    spread = (piece_end - min(last.values())) / max(1.0, piece_end)
    out.append(_finding(
        "ending_voices", "medium",
        _where(spec, min(last.values()), inst=order[0][0]),
        f"多编制收束：各声部结束时间差 {round(spread * 100, 1)}% 曲长"
        f"（ending_voices {ve}，偏低）",
        "让低音先收、旋律后收，或末音渐弱（不自动改，由 AI 选）",
        "改后运行 `mscli ms report task.json --json`：ending_voices ≥ 0.35"))
    return out


def _technique(spec, intent, report):
    out = []
    tech = (intent or {}).get("technique") or {}
    if not tech.get("density"):
        return out
    notes = spec.get("notes") or []
    marked = [n for n in notes if n.get("articulation") or n.get("ornament")]
    if not marked or not notes:
        return out
    ratio = len(marked) / len(notes)
    limit = {"low": 0.15, "medium": 0.4, "high": 1.0}.get(
        str(tech["density"]).lower(), 1.0)
    if ratio > limit:
        out.append(_finding(
            "technique_density", "medium",
            _where(spec, marked[-1].get("beat", 0), inst=marked[-1].get("inst", 1)),
            f"奏法/转折 {len(marked)}/{len(notes)}（{round(ratio * 100, 1)}%）"
            f"超过密度意图 {tech['density']} 上限 {round(limit * 100)}%",
            "删掉部分奏法，或把 intent 密度调到 medium/high",
            "改后重跑 `mscli ms diagnose task.json --intent intent.json`：不再出现 technique_density"))
    return out


def _structure(spec, intent, report):
    out = []
    st = (intent or {}).get("structure") or {}
    target = st.get("total_bars") or (sum(st["section_bars"]) if st.get("section_bars") else None)
    if not target:
        return out
    notes = spec.get("notes") or []
    meter = tuple(spec.get("meter") or (4, 4))
    bpb = max(1, int(meter[0]))
    actual = max([float(n.get("beat", 0)) + float(n.get("beats", 1)) for n in notes] or [0.0])
    bars = max(1, int(actual // bpb + (1 if actual % bpb else 0)))
    if abs(bars - int(target)) > max(2, int(0.2 * int(target))):
        out.append(_finding(
            "structure_bars", "medium", {"bar": 1, "beat": 0.0},
            f"结构目标 {target} 小节，实际 {bars} 小节（偏差过大）",
            "补/删段落或调整小节数（由 AI 决定音乐上怎么补）",
            "改后重跑 `mscli ms diagnose task.json --intent intent.json`：不再出现 structure_bars"))
    return out


def _intent_deviation(report):
    out = []
    ic = report.get("intent_check") or {}
    for layer, info in (ic.get("layers") or {}).items():
        if info.get("status") == "偏离":
            out.append(_finding(
                f"intent_{layer}", "low", {"scope": "全曲"},
                f"意图层「{layer}」偏离：{info.get('detail') or ''}",
                "按报告中的测量值调整对应参数（AI 判断具体改法）",
                "改后重跑 `mscli ms report task.json --json` 看该层是否回到「符合」"))
    return out


def findings_for(spec: dict, report: dict, intent=None) -> list:
    """纯计算：由 spec + report 得 findings（供 report 复用，不 build）。"""
    if not isinstance(intent, dict):
        intent = None
    findings = []
    findings += _overlaps(spec)
    findings += _pedal_gaps(spec)
    findings += _ending(spec, report)
    findings += _technique(spec, intent, report)
    findings += _structure(spec, intent, report)
    findings += _intent_deviation(report)
    sev_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: sev_order.get(f["severity"], 9))
    return findings


def summary_text(findings: list) -> str:
    lines = [f"诊断：{len(findings)} 条"]
    for f in findings:
        w = f["where"]
        loc = ", ".join(f"{k}={v}" for k, v in w.items())
        lines.append(f"  [{f['severity']}] {f['code']} @ {loc}")
        lines.append(f"      原因：{f['why']}")
        lines.append(f"      建议：{f['suggestion']}")
        lines.append(f"      复核：{f['verify']}")
    if not findings:
        lines.append("  未发现可定位的问题（可继续听/看谱判断）")
    return "\n".join(lines)


def diagnose(spec_or_song, *, intent=None) -> dict:
    """返回 {ok, findings, summary}；只诊断，不改 spec。"""
    spec = _spec_of(spec_or_song)
    if not isinstance(intent, dict):
        intent = None
    import ms
    try:
        song = ms.build(spec)
        report = ms.report(song, intent=intent, include_diagnosis=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "findings": [],
                "summary": f"生成失败，无法诊断：{exc}"}
    findings = findings_for(spec, report, intent)
    return {"ok": True, "findings": findings,
            "summary": summary_text(findings)}


__all__ = ["diagnose", "findings_for", "summary_text"]
