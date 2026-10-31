# -*- coding: utf-8 -*-
"""意图 → 初稿任务 JSON：给 AI 一个可编辑的骨架，不用从空白开始。

用法：
    spec = ms.draft({"structure": {"section_bars": [8, 8, 16, 8]},
                     "expression": {"expectation": 0.8},
                     "technique": {"density": "low"}})
    song = ms.build(spec)      # 初稿；AI 再改音符
"""
from __future__ import annotations

LEVELS = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
MELODY = ["C4", "D4", "E4", "G4", "A4", "E4", "D4", "C4"]
BASS = ["C3", "C3", "F3", "G3"]


def _level(t: float) -> str:
    return LEVELS[min(len(LEVELS) - 1, int(round(t * (len(LEVELS) - 1))))]


def draft(intent=None, *, bars: int | None = None, bpm: float = 90.0,
          meter=(4, 4), instruments=None) -> dict:
    """按意图生成一版骨架 spec（有结构、有力度弧线、有基本音符）。"""
    intent = dict(intent or {})
    st = intent.get("structure") or {}
    sb = st.get("section_bars")
    if isinstance(sb, list) and sb:
        sections = [max(1, int(x)) for x in sb]
    else:
        total = int(bars or st.get("total_bars") or 16)
        total = max(4, total)
        base = max(2, total // 4)
        sections = [base] * 3 + [max(1, total - base * 3)]
    total_bars = sum(sections)

    exp = float((intent.get("expression") or {}).get("expectation", 0.5))
    exp = max(0.0, min(1.0, exp))
    density = str((intent.get("technique") or {}).get("density") or "low").lower()

    insts = list(instruments or [{"type": "piano"}])
    if len(insts) == 1 and total_bars >= 16:
        insts = [{"type": "piano"}, {"type": "cello"}]

    bpb = int(meter[0])
    peak = 0.45 + 0.35 * exp
    peak_bar = int(round(peak * max(1, total_bars - 1)))
    # 段落对比：音符数/音区偏移/节奏型
    SEC_PAT = [(2, 0, "even"), (3, 5, "dotted"), (4, 0, "even"),
               (1, -5, "half"), (3, 2, "sync")]
    notes = []
    bar = 0
    for si, blen in enumerate(sections):
        n_per, shift, rhythm = SEC_PAT[si % len(SEC_PAT)]
        for b in range(blen):
            t = bar / max(1, total_bars - 1)
            tens = 1.0 - abs(t - peak) / max(1e-6, peak if t <= peak else 1 - peak)
            tens = max(0.15, min(1.0, tens))
            lv = _level(tens)
            beat = bar * bpb
            # 段尾留白（最后一小节只写前半），帮助分段
            tail = (b == blen - 1)
            slots = n_per if not tail else max(1, n_per // 2)
            for k in range(slots):
                if rhythm == "dotted":
                    pos = k * bpb * 0.75
                elif rhythm == "sync":
                    pos = k * bpb / max(1, slots) + (0.25 if k % 2 else 0)
                else:
                    pos = k * bpb / max(1, slots)
                pitch = MELODY[(bar + k * 2 + shift) % len(MELODY)]
                base = {"C4": 0, "D4": 2, "E4": 4, "G4": 7, "A4": 9}
                _NAMES = ["C", "C#", "D", "D#", "E", "F", "F#",
                          "G", "G#", "A", "A#", "B"]
                st = base.get(pitch[:2], 0)
                semi = 60 + st + shift
                name = _NAMES[semi % 12] + str(semi // 12 - 1)
                notes.append({"inst": 1, "pitch": name,
                              "beat": beat + pos,
                              "beats": min(bpb / max(1, slots), 1.0),
                              "level": lv})
            if len(insts) > 1:
                notes.append({"inst": 2,
                              "pitch": BASS[(bar + shift) % len(BASS)],
                              "beat": beat, "beats": bpb * (0.5 if tail else 1.0),
                              "level": lv})
            bar += 1

    # 技术密度：low 只在每 4 小节加 1 个；medium 每 2 小节；high 每小节
    step = {"low": 4, "medium": 2, "high": 1}.get(density, 4)
    for i in range(0, min(len(notes), total_bars * 2), step * 2):
        if density != "low" or i < total_bars:
            notes[i]["articulation"] = "staccato"

    # 收束：多编制时让低音先收、旋律后收（避免同时停）
    if len(insts) > 1:
        last = notes[-1]
        last["beats"] = max(1, bpb / 2)

    total_beats = total_bars * bpb
    curves = [{"inst": 1, "param": "dynamics",
               "points": [[0, 500], [peak_bar * bpb, 950], [total_beats, 450]]}]
    return {"bpm": float(bpm), "meter": list(meter), "instruments": insts,
            "notes": notes, "curves": curves}


__all__ = ["draft"]
