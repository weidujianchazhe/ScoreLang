# -*- coding: utf-8 -*-
"""分析报告：给一首曲子做结构与演奏分析。"""
from __future__ import annotations


def report(spec_or_song, *, intent: dict | None = None,
           include_diagnosis: bool = True) -> dict:
    """`ms.report(spec)` / `ms.report(song)` → {summary, quality, capability, sections, diagnosis?}。"""
    from .task import Song, build

    song = build(spec_or_song) if isinstance(spec_or_song, dict) else spec_or_song
    if not isinstance(song, Song):
        raise TypeError("需要 spec dict 或 Song")
    from ms_to_s02 import to_s02
    from s02_api import build_payload
    from s02_capability import analyze as _capability
    from s02_quality import analyze as _quality

    tb = int(round(60_000_000 / song.bpm))
    score, _rep = to_s02(song._doc, time_base_us=tb)
    payload = build_payload(score)
    quality = _quality(payload)
    out = {"summary": song.summary(),
           "quality": quality,
           "capability": _capability(song._doc),
           "sections": payload.get("sections", [])}
    if intent:
        try:
            from s02_intent import compare as _intent
            out["intent_check"] = _intent(intent, quality)
        except Exception as exc:  # noqa: BLE001
            out["intent_check"] = {"error": str(exc)}
    if include_diagnosis:
        spec = getattr(song, "_spec", None)
        if isinstance(spec, dict):
            try:
                from .diagnose import findings_for, summary_text
                fs = findings_for(spec, out, intent)
                out["diagnosis"] = {"findings": fs, "summary": summary_text(fs)}
            except Exception as exc:  # noqa: BLE001
                out["diagnosis"] = {"error": str(exc)}
    return out


def text(rep: dict) -> str:
    """把 report dict 变成人类的简短文本（含诊断位置）。"""
    lines = []
    s = rep.get("summary") or {}
    lines.append("摘要：" + " · ".join(f"{k}={v}" for k, v in s.items()))
    q = rep.get("quality") or {}
    m = q.get("metrics") or {}
    if m:
        lines.append("指标：" + " ".join(f"{k}={v}" for k, v in m.items()))
    diag = rep.get("diagnosis") or {}
    fs = diag.get("findings") or []
    if fs:
        lines.append(f"诊断：{len(fs)} 条")
        for f in fs:
            w = f.get("where") or {}
            loc = " ".join(f"{k}={v}" for k, v in w.items())
            lines.append(f"  [{f['severity']}] {f['code']} @ {loc}：{f['why']}；"
                         f"建议 {f['suggestion']}；复核：{f['verify']}")
    elif diag:
        lines.append("诊断：未发现可定位的问题")
    return "\n".join(lines)


__all__ = ["report"]
