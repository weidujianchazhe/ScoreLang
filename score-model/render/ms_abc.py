# -*- coding: utf-8 -*-
"""MS → ABC 谱（导出用）。"""
from __future__ import annotations

# ABC 音名：C D E F G A B；半音用 ^ / _ 前缀；八度用 , / ' 相对 C4
_LETTER = {"C": "C", "D": "D", "E": "E", "F": "F", "G": "G", "A": "A", "B": "B"}


def _abc_pitch(pitch) -> str:
    letter = _LETTER[pitch.step]
    acc = ""
    if pitch.alter > 0:
        acc = "^" * int(pitch.alter)
    elif pitch.alter < 0:
        acc = "_" * int(-pitch.alter)
    octv = int(pitch.octave) - 4          # C4 = 无后缀
    if octv > 0:
        return letter + "'" * octv
    if octv < 0:
        return letter + "," * (-octv)
    return letter


def _abc_len(beats: float, unit_beats: float) -> str:
    """时值 → ABC 长度后缀（L: unit_beats）。"""
    units = beats / unit_beats
    if abs(units - round(units)) < 1e-3:
        n = int(round(units))
        return "" if n == 1 else str(n)
    # 常见分数：1/2、1/4、3/2…
    for den in (2, 3, 4, 6, 8, 12, 16):
        num = units * den
        if abs(num - round(num)) < 1e-3 and num >= 1:
            n = int(round(num))
            return f"{'' if n == 1 else n}/{den}"
    return "1"     # 兜底


def to_abc(doc, *, title: str = "", bpm: float = 120.0,
           meter=(4, 4), unit_note: float = 0.5) -> str:
    """`MSDocument` → ABC 文本。

    · 每件乐器一个声部（V:1、V:2…），按 `instrument_id` 分组；
    · 按起点排序，空隙补休止 `z`；同起点同值写成和弦 `[C E G]`；
    · `unit_note` 是 L 的长度（拍）：0.5 = 八分音符。
    """
    if bpm <= 0:
        raise ValueError("bpm 必须为正")
    us_per_beat = 60_000_000 / bpm
    unit_beats = float(unit_note)
    num, den = meter
    fifths = 0

    l_den = int(round(4.0 / unit_beats))   # whole = 4 拍；L:1/8 = 八分音符
    lines = ["X:1", f"T:{title or 'MS export'}", f"M:{num}/{den}",
             f"L:1/{l_den}", f"Q:1/4={int(round(bpm))}", "K:C"]

    by_inst: dict = {}
    for e in doc.events:
        by_inst.setdefault(e.instrument_id, []).append(e)

    for iid in sorted(by_inst):
        evs = sorted(by_inst[iid], key=lambda e: (e.onset_us, e.release_us or e.onset_us))
        lines.append(f"V:{iid} name=\"P{iid}\"")
        out, cursor = [], 0.0
        i = 0
        while i < len(evs):
            onset = evs[i].onset_us / us_per_beat
            if onset > cursor + 1e-6:
                out.append("z" + _abc_len(onset - cursor, unit_beats))
                cursor = onset
            # 同起点同值的音 → 和弦
            group = [evs[i]]
            j = i + 1
            while j < len(evs) and abs(evs[j].onset_us - evs[i].onset_us) < 1:
                group.append(evs[j])
                j += 1
            dur = (group[0].release_us - group[0].onset_us) / us_per_beat
            names = [_abc_pitch(e.pitch) for e in group]
            token = names[0] if len(names) == 1 else "[" + " ".join(names) + "]"
            out.append(token + _abc_len(max(dur, 1e-6), unit_beats))
            cursor = max(cursor, onset + dur)
            i = j
        lines.extend(" ".join(out[k:k + 8]) for k in range(0, len(out), 8))
    return "\n".join(lines) + "\n"


__all__ = ["to_abc"]
